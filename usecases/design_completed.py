"""Use case: design-completed.

When an Ounass Product Design (OPD) ticket reaches Done, print a single Slack message
listing the newly-completed tickets — once per ticket. The routine posts that message to
one channel it names in its prompt (slot-watch style: stdout is the message).

The script owns all business logic (the JQL, the field list, dedup, formatting). Claude
only runs the query the script emits and posts the message it prints. Two subcommands:

    query    -> prints {"jql": ..., "fields": [...]} for Claude to run via jira-rest
    render   -> reads the JQL result rows on stdin, prints the Slack message,
                records the emitted keys as sent (empty output = nothing new)

Field mapping (verified against OPD-3):
    summary       -> summary
    designer      -> customfield_12707  (Product Owner)
    figma link(s) -> customfield_12714  (Design)
    completed_on  -> customfield_13239  (Actual Design/Research Finish Date),
                     falling back to statuscategorychangedate (went Done)

Output uses standard markdown ([label](url), **bold**) — the format the Slack connector
renders. Slack's native <url|label> would post literally.
"""
import json
from datetime import datetime

from core import gitstate

PROJECT = "OPD"
RECENCY_DAYS = 7
BROWSE = "https://altayerdigital.atlassian.net/browse/%s"
STATE_PATH = "state/design_completed.json"

F_SUMMARY = "summary"
F_DESIGNER = "customfield_12707"
F_FIGMA = "customfield_12714"
F_DESIGN_FINISH = "customfield_13239"
F_DONE_TS = "statuscategorychangedate"

QUERY_FIELDS = [F_SUMMARY, F_DESIGNER, F_FIGMA, F_DESIGN_FINISH, F_DONE_TS]


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


def extract_ticket(issue):
    """Normalise a raw jira-rest issue into the fields we display."""
    f = issue.get("fields", {}) or {}
    owners = f.get(F_DESIGNER) or []
    designer = ", ".join(o.get("displayName", "") for o in owners if o.get("displayName"))
    figma = [(d.get("displayName") or d.get("url"), d.get("url"))
             for d in (f.get(F_FIGMA) or []) if d.get("url")]
    completed_on = _fmt_date(f.get(F_DESIGN_FINISH)) or _fmt_date(f.get(F_DONE_TS))
    return {
        "key": issue.get("key"),
        "summary": f.get(F_SUMMARY) or "",
        "designer": designer,
        "figma": figma,
        "completed_on": completed_on,
    }


def _md_link(url, label):
    return "[%s](%s)" % (label, url)


def _ticket_lines(t):
    lines = ["• %s — %s" % (_md_link(BROWSE % t["key"], t["key"]), t["summary"])]
    meta = []
    if t["designer"]:
        meta.append("👤 %s" % t["designer"])
    if t["completed_on"]:
        meta.append("📅 %s" % t["completed_on"])
    if meta:
        lines.append("   " + " · ".join(meta))
    for label, url in t["figma"]:
        lines.append("   🔗 %s" % _md_link(url, label))
    if not t["figma"]:
        lines.append("   🔗 _no Figma link on ticket_")
    return lines


def format_message(tickets):
    """Render all tickets into one Slack message body."""
    lines = ["🎨 **Design completed**"]
    for t in tickets:
        lines.extend(_ticket_lines(t))
    return "\n".join(lines)


def render(issues, sent_keys):
    """Filter already-sent tickets and return (message string, newly-emitted keys).
    Empty message when there is nothing new."""
    new = [extract_ticket(i) for i in issues if i.get("key") not in sent_keys]
    if not new:
        return "", []
    return format_message(new), [t["key"] for t in new]


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
