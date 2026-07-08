# Product Master Routines — Design Spec

**Repo:** `github.com/dgolani/product-master-routines`
**Date:** 2026-07-08
**Author:** Dinesh Golani (with Claude)
**Status:** Draft for review

---

## 1. Goal

A single master script (`pm.py`) that backs a **family** of Claude routines for product
management. Each use case is one mode of the script and maps to one routine. Use cases are
isolated — adding one never touches another — so they stay clearly differentiated and cannot
conflict.

Modeled on the proven `ounass_slots.py` slot-watch routine (mode dispatch via `argv`, git-committed
state, stdout-is-the-message contract).

First use case: **`design-completed`** — when an Ounass Product Design (OPD) ticket reaches Done,
post a Slack alert to the channel mapped to the ticket's POD, **once per ticket**.

---

## 2. Core principle — "script = brain, Claude = hands"

A routine runs the script as a **subprocess Claude launches**. That subprocess **cannot** call
Claude's MCP connectors (jira-rest, Slack, etc.) and has no injected DB/Slack credentials. So:

- **Script owns all business logic** (deterministic, testable, version-controlled): the query, the
  field list, dedup / "send once", POD→channel routing, message formatting.
- **Claude does only the two I/O things the subprocess cannot reach**: run the query the script
  emits (via the jira connector) and post the blocks the script prints (via the Slack connector).

The routine prompt contains **no logic, no query text, no channel IDs** — all of that lives in the
script.

### Single-connector decision (from the dry run)

The dry run on real ticket OPD-3 showed the Figma link lives **only** in the live Jira field
`customfield_12714` — it is **not** in the `opd_jira` MySQL replica. jira-rest also already provides
summary, POD, Product Owner, and the done-timestamp. Therefore this use case uses **jira-rest / JQL
only**; the MySQL connector is dropped. The originally-supplied SQL is not used.

---

## 3. Repo layout

```
product-master-routines/
  pm.py                          # entry point + dispatcher: MODE = sys.argv[1]
  usecases/
    design_completed.py          # use case #1 (self-contained)
  core/
    gitstate.py                  # git-committed state lifted from ounass_slots.py
  state/
    design_completed.json        # git-committed "already sent" keys
  docs/specs/                     # this spec
```

`pm.py` is a thin registry: `USE_CASES = {"design-completed": design_completed.run}`. A new use case =
a new module in `usecases/` + one registry line. Zero blast radius on existing use cases — this is
the non-conflicting / differentiated guarantee.

---

## 4. `design-completed` contract

Two subcommands, driven by the routine prompt:

```
python3 pm.py design-completed query
    → prints a small JSON object: { "jql": "...", "fields": ["...", ...] }
      (the exact JQL to run + the Jira fields to request). Nothing else.

python3 pm.py design-completed render         # ← JQL result rows as JSON on stdin
    → drops any ticket key already in state/design_completed.json
    → prints one block per new epic: a postable message with a {{SUMMARY}} slot + a
      MATERIAL section (description + linked product epic) for Claude to write the summary
    → records the emitted keys as sent (git commit + push; fail-open like should_send_alert)
    → empty output = nothing new
```

Routing note: there is **no POD→channel mapping**. All alerts go to a single channel that
the routine names in its prompt (slot-watch style). The script owns the fixed fields; Claude
writes only the 3-4 line summary and posts.

### `query` output (JQL, not SQL)

```json
{
  "jql": "project = OPD AND status = Done AND statusCategoryChangedDate >= -7d ORDER BY statusCategoryChangedDate DESC",
  "fields": ["summary", "description", "customfield_12707", "customfield_12714",
             "customfield_13239", "statuscategorychangedate", "issuelinks"]
}
```

- **7-day recency guard** bounds the working set.
- Field list is owned by the script, so the prompt never names a field id.

### `render` output (one block per new epic)

Standard markdown (`[label](url)`, `**bold**`) — the Slack connector's format. Claude fills
`{{SUMMARY}}` and posts the lines above `===MATERIAL` only.

```
===MESSAGE===
🎨 **Design completed**
• [OPD-3](https://altayerdigital.atlassian.net/browse/OPD-3) — Search-Integrated Dynamic Edit Pages
   👤 Dawid Tomczyk · 📅 07 Jul 2026
   🔗 [VM platform - Phase 4 - Automated edit pages](https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730)
   📋 Feature epic: [VM-527](https://altayerdigital.atlassian.net/browse/VM-527)
   📝 {{SUMMARY}}
===MATERIAL (do not post — use it to write {{SUMMARY}})===
Design epic description: New feature will allow merchandisers to create trend edit pages…
Linked product epic(s):
- VM-527: [pod_vm] Search-Integrated Dynamic Edit Pages
===END===
```

---

## 5. Field mapping (verified in dry run on OPD-3)

| Display field | Source | Notes |
|---|---|---|
| Summary | `summary` | |
| Description | `description` | Summary material (may be a Confluence smartlink) |
| Figma link(s) | `customfield_12714` ("Design") | Array of `{displayName, url}`; render all links |
| Designer | `customfield_12707` ("Product Owner") | Array of users; join display names |
| Completed-on | `customfield_13239` ("Actual Design/Research Finish Date") | If null → fall back to `statuscategorychangedate` (when it entered Done) |
| Product epic(s) | `issuelinks` | Linked Epics **not** in the OPD project (e.g. VM-527). May be absent |
| Ticket key | issue `key` | Dedup key + `browse/` link |

Cloud site: `altayerdigital.atlassian.net` (cloudId `ca815d59-7877-4488-8456-8511e1ade88a`),
project **OPD** = "Ounass Product Design" (id 13168).

---

## 6. Dedup & cold-start

- **Dedup:** `state/design_completed.json` holds the set of ticket keys already alerted. `render`
  filters these out and records newly-emitted keys via git commit + push (reusing the slot-watch
  `gitstate` helpers). **Fail-open**: if state can't be read/written, we still emit — matching the
  existing routine's behaviour. Guarantee: at most one alert per ticket key.
- **Cold-start:** on the first run with no/empty state file, **backfill silently** — record all
  currently-Done keys (within the 7-day window) as sent and post nothing — so we don't blast the
  backlog on day one.

---

## 7. Routing

No routing config. All alerts go to a **single channel** named in the routine prompt
(slot-watch style). To change the destination, edit the prompt — not the code.

---

## 8. Routine prompt (the entire prompt — direction + comms only)

Replace `<CHANNEL>` with the target channel name/id (or a person).

```
1. From the repo root, run: python3 pm.py design-completed query
   Parse stdout as JSON { jql, fields }. Run that JQL via the jira-rest connector,
   requesting exactly those fields.
2. Pipe the resulting issues as JSON into stdin of: python3 pm.py design-completed render
3. The script prints zero or more blocks, each between "===MESSAGE===" and "===END===".
   For each block:
     a. Read the MATERIAL section; write a 3-4 line summary of what the feature is about.
        If a product epic is linked, you may open it (and any Confluence page it references)
        to get the real description.
     b. Replace {{SUMMARY}} with your summary.
     c. Post the lines between "===MESSAGE===" and "===MATERIAL" VERBATIM to <CHANNEL>.
        Do NOT post the MATERIAL section.
   If there are no blocks, do nothing.
```

Schedule: TBD (e.g. hourly, like slot-watch). Connectors granted to the routine: **jira-rest**
(or jiraanalysis) + **Slack** + **Confluence** (to follow linked wiki pages).

---

## 9. Decisions locked

- Designer = Product Owner (`customfield_12707`).
- Completed-on = `customfield_13239`, falling back to `statuscategorychangedate`.
- Scope = any OPD issue at Done, 7-day recency guard; issue-type restriction deferrable later.
- Single data source: jira-rest (MySQL query dropped); Confluence used only to enrich summaries.
- Dedup = git state file, recorded at `render`, fail-open.
- Feature summary is Claude-written (3-4 lines) via a `{{SUMMARY}}` slot the script emits;
  fixed fields + linked product-epic link stay script-owned. Product epic may be absent.

---

## 10. Out of scope / future

- Real POD→channel mapping (test phase DMs Dinesh only).
- Additional use cases (each = new `usecases/` module + registry line + its own routine).
- Optional hardening: record-after-post dedup (3rd `commit` call) if a missed alert ever proves
  costlier than a rare duplicate.
```
