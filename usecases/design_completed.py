"""Use case: design-completed.

When an Ounass Product Design (OPD) ticket reaches Done, print a Slack message per
newly-completed epic — once per ticket. Each message carries the fixed fields plus a
3-4 line summary of *what the feature is about*, which Claude writes from the material
the script assembles (the design epic's description + its linked product epic, and any
Confluence page that epic references).

The script owns everything deterministic: the JQL, the field list, dedup, the linked
product-epic detection, the message layout, and the raw material. Claude owns only the
prose summary (a genuinely non-deterministic, reasoning task) and the posting.

Subcommands:
    query    -> prints {"jql", "fields"} to run via jira-rest
    render   -> reads JQL rows on stdin, prints one block per new epic, records sent keys

Each block:
    ===MESSAGE===
    <postable message, with a {{SUMMARY}} slot>
    ===MATERIAL (do not post)===
    <description + linked product epic, for writing the summary>
    ===END===
Claude fills {{SUMMARY}} and posts the postable part only.

Field mapping (verified against OPD-3 / VM-527):
    summary       -> summary
    description   -> description                (summary material)
    designer      -> customfield_12707          (Product Owner)
    figma link(s) -> customfield_12714          (Design)
    completed_on  -> customfield_13239, else statuscategorychangedate
    product epic  -> issuelinks (linked Epics not in the OPD project)

Output uses standard markdown ([label](url), **bold**) — the Slack connector's format.
"""
import json
from datetime import datetime

from core import gitstate

PROJECT = "OPD"
RECENCY_DAYS = 7
BROWSE = "https://altayerdigital.atlassian.net/browse/%s"
STATE_PATH = "state/design_completed.json"

F_SUMMARY = "summary"
F_DESCRIPTION = "description"
F_DESIGNER = "customfield_12707"
F_FIGMA = "customfield_12714"
F_DESIGN_FINISH = "customfield_13239"
F_DONE_TS = "statuscategorychangedate"
F_LINKS = "issuelinks"

QUERY_FIELDS = [F_SUMMARY, F_DESCRIPTION, F_DESIGNER, F_FIGMA,
                F_DESIGN_FINISH, F_DONE_TS, F_LINKS]


def build_query():
    """Return the JQL + fields for Claude to run via the jira connector."""
    jql = ("project = %s AND status = Done AND statusCategoryChangedDate >= -%dd "
           "ORDER BY statusCategoryChangedDate DESC" % (PROJECT, RECENCY_DAYS))
    return {"jql": jql, "fields": list(QUERY_FIELDS)}


def _fmt_date(value):
    """'2026-07-07T09:24:00.363+0400' or '2026-07-05' -> '07 Jul 2026'. '' if unparseable."""
    if not value:
        return ""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return ""


def _product_epics(f):
    """Linked issues that are Epics outside the OPD (design) project = product/feature
    epics. Returns [{key, summary, url}] (empty if none — not every design epic has one)."""
    out = []
    for link in f.get(F_LINKS) or []:
        li = link.get("outwardIssue") or link.get("inwardIssue") or {}
        key = li.get("key")
        lf = li.get("fields") or {}
        itype = (lf.get("issuetype") or {}).get("name")
        if not key or itype != "Epic" or key.startswith(PROJECT + "-"):
            continue
        out.append({"key": key, "summary": lf.get("summary") or "", "url": BROWSE % key})
    return out


def extract_ticket(issue):
    """Normalise a raw jira-rest issue into display fields + summary material."""
    f = issue.get("fields", {}) or {}
    owners = f.get(F_DESIGNER) or []
    designer = ", ".join(o.get("displayName", "") for o in owners if o.get("displayName"))
    figma = [(d.get("displayName") or d.get("url"), d.get("url"))
             for d in (f.get(F_FIGMA) or []) if d.get("url")]
    completed_on = _fmt_date(f.get(F_DESIGN_FINISH)) or _fmt_date(f.get(F_DONE_TS))
    return {
        "key": issue.get("key"),
        "summary": f.get(F_SUMMARY) or "",
        "description": f.get(F_DESCRIPTION) or "",
        "designer": designer,
        "figma": figma,
        "completed_on": completed_on,
        "product_epics": _product_epics(f),
    }


# House style for the alert (chosen: casual teammate update, light emoji, inline links).
STYLE_NOTE = ("Casual teammate Slack update — sound like a real person sharing good news, "
              "not a bot. One light emoji is fine. Links inline as [text](url). Write a "
              "2-3 sentence, plain-language summary of what the feature is and why it matters. "
              "Drop the build/epic clause entirely if there is no product epic.")

SHAPE = ("🎉 Design's wrapped on **[<title>](<design ticket url>)** — <designer> finished it on <date>.\n"
         "<2-3 sentences: what the feature is and why it matters>\n"
         "Designs are in [Figma](<figma url>), build's tracked in [<epic>](<epic url>).")


def _facts_lines(t):
    lines = ["- title: %s" % t["summary"],
             "- design ticket url: %s" % (BROWSE % t["key"])]
    if t["designer"]:
        lines.append("- designer: %s" % t["designer"])
    if t["completed_on"]:
        lines.append("- completed: %s" % t["completed_on"])
    if t["figma"]:
        for label, url in t["figma"]:
            lines.append("- figma: %s | %s" % (label, url))
    else:
        lines.append("- figma: none")
    if t["product_epics"]:
        for pe in t["product_epics"]:
            lines.append("- product epic: %s | %s" % (pe["key"], pe["url"]))
    else:
        lines.append("- product epic: none (skip the build/epic clause)")
    return lines


def _material_lines(t):
    lines = ["Design epic description: %s" % (t["description"].strip() or "(none)")]
    if t["product_epics"]:
        lines.append("Linked product epic(s):")
        for pe in t["product_epics"]:
            lines.append("- %s: %s" % (pe["key"], pe["summary"]))
    else:
        lines.append("Linked product epic(s): none — summarise from the design epic description above.")
    return lines


def format_block(t):
    """One epic -> a brief for Claude: STYLE + SHAPE + exact FACTS + SUMMARY MATERIAL.
    Claude writes the human-voice message from this and posts it (no verbatim slice)."""
    return "\n".join(
        ["===EPIC %s===" % t["key"],
         "STYLE: " + STYLE_NOTE,
         "SHAPE (match the tone, write your own words — do not copy the placeholders):",
         SHAPE,
         "",
         "FACTS (use exactly; never change names, dates, or links):"]
        + _facts_lines(t)
        + ["",
           "SUMMARY MATERIAL (write the summary from this; open the product epic / its "
           "Confluence page if it is thin):"]
        + _material_lines(t)
        + ["===END==="]
    )


def render(issues, sent_keys):
    """Filter already-sent tickets and return (blocks string, newly-emitted keys).
    Empty string when there is nothing new."""
    new = [extract_ticket(i) for i in issues if i.get("key") not in sent_keys]
    if not new:
        return "", []
    return "\n\n".join(format_block(t) for t in new), [t["key"] for t in new]


def select_output(out, new_keys, is_first_run):
    """Cold-start guard: on the first run (no state file yet) suppress output but still
    record the keys, so we don't blast the backlog. Returns (output, keys_to_record)."""
    if is_first_run:
        return "", new_keys
    return out, new_keys


def coerce_issues(payload):
    """Accept the common jira-connector result shapes and return a flat list of issues:
    a plain list, {"issues": [...]}, or {"issues": {"nodes": [...]}}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        issues = payload.get("issues", payload.get("nodes", []))
        if isinstance(issues, dict):
            return issues.get("nodes", [])
        return issues or []
    return []


def run(sub, stdin_text="", state_path=STATE_PATH):
    """Entry point invoked by pm.py. `sub` is 'query' or 'render'. Returns the string to
    print (empty string = print nothing)."""
    if sub == "query":
        return json.dumps(build_query(), indent=2)

    if sub == "render":
        issues = coerce_issues(json.loads(stdin_text)) if stdin_text.strip() else []
        first_run = not gitstate.state_exists(state_path)
        sent = gitstate.load_sent(state_path)
        out, new_keys = render(issues, sent)
        final_out, record = select_output(out, new_keys, first_run)
        if record:
            gitstate.save_sent(state_path, sent | set(record),
                               "chore(design-completed): record %d sent" % len(record))
        return final_out

    raise ValueError("unknown subcommand: %s (expected 'query' or 'render')" % sub)
