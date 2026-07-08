# product-master-routines

One master script (`pm.py`) backing a **family** of Claude routines for product management.
Each use case is one mode of the script and maps to one routine. Use cases are isolated —
adding one never touches another — so they stay clearly differentiated and cannot conflict.

Modeled on the `ounass_slots.py` slot-watch routine: mode dispatch, git-committed state,
**stdout is the message** (empty stdout = do nothing).

## Principle: script = brain, Claude = hands

A routine runs `pm.py` as a subprocess. That subprocess **cannot** call Claude's MCP
connectors and has no injected credentials. So:

- **The script owns all business logic** — the query, the field list, dedup, formatting.
- **Claude does only the I/O the subprocess can't reach** — run the query the script emits
  (via a connector) and post the message it prints (to Slack).

The routine prompt contains no logic and no query — just which connector to run and which
channel to post to.

## Layout

```
pm.py                       # entry point + dispatcher (USE_CASES registry)
usecases/design_completed.py# use case #1
core/gitstate.py            # git-committed state (shared)
state/design_completed.json # created on first run (git-committed dedup)
tests/                      # unittest (stdlib, no pip installs)
docs/specs/                 # design spec
```

## Adding a use case

1. Add `usecases/<name>.py` exposing `run(sub, stdin_text, ...)`.
2. Register it: `USE_CASES = {"<name>": <module>.run, ...}` in `pm.py`.
3. Create a routine pointing at it (below). Existing use cases are untouched.

## Use case: `design-completed`

Alerts when OPD design epics reach Done — once per ticket. Each alert carries the fixed
fields plus a 3-4 line summary of *what the feature is about*, which Claude writes from the
material the script assembles. The routine posts to a single channel named in its prompt.

```
python3 pm.py design-completed query    # prints {"jql", "fields"} to run via jira-rest
python3 pm.py design-completed render     # reads JQL rows (JSON) on stdin, prints one block
                                         # per new epic, records sent keys
```

`render` prints, per new epic, a **brief** — style + exact facts + summary material — that
Claude turns into a human-voice Slack message:

```
===EPIC OPD-3===
STYLE: casual teammate update, light emoji, inline links, 2-3 sentence summary…
SHAPE (match the tone, write your own words): 🎉 Design's wrapped on **[<title>](…)** …
FACTS (use exactly): title / design ticket url / designer / completed / figma / product epic
SUMMARY MATERIAL (open the product epic / its Confluence page if thin): <description> …
===END===
```

- **Dedup:** `state/design_completed.json` (git-committed), fail-open. At most one alert per key.
- **Cold-start:** first run with no state file records all current keys silently (no backlog blast).
- **Facts (script-owned, exact):** title · design-ticket link · designer (Product Owner) ·
  completed-on · Figma link(s) · linked product epic (when present).
- **Message (Claude-written):** a casual, human 2-3 sentence write-up in the house style, using
  the facts verbatim; Claude may open the product epic / its Confluence page for the summary.

### Routine setup

- **Repo:** this repo. **Connectors:** jira-rest (or jiraanalysis) + Slack + **Confluence**
  (for following linked wiki pages). **Schedule:** e.g. hourly.
- **Prompt** (replace `<CHANNEL>` with your channel name/id or a person):

```
1. From the repo root, run: python3 pm.py design-completed query
   Parse stdout as JSON { "jql", "fields" }. Run that JQL via the jira-rest connector,
   requesting exactly those fields.
2. Pipe the resulting issues as JSON into stdin of:
   python3 pm.py design-completed render
3. The script prints zero or more briefs, each between "===EPIC …===" and "===END===".
   For each brief, write ONE Slack message and post it to <CHANNEL>:
     - Follow the STYLE and SHAPE (casual, human — your own words, not a template).
     - Use the FACTS exactly (never change names, dates, or links).
     - Write the 2-3 sentence summary yourself from the SUMMARY MATERIAL; if a product epic
       is linked, you may open it (and any Confluence page it references) for the real detail.
   Post only your composed message — never the brief itself. If there are no briefs, do nothing.
```

## Tests

```
python3 -m unittest discover -s tests
```
