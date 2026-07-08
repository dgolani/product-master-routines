"""Use case: design-completed.

When an Ounass Product Design (OPD) ticket reaches Done, alert the Slack channel mapped
to the ticket's POD — once per ticket.

The script owns all business logic (the JQL, the field list, dedup, routing, formatting).
Claude only runs the query the script emits and posts the blocks it prints. Two subcommands:

    query    -> prints {"jql": ..., "fields": [...]} for Claude to run via jira-rest
    render   -> reads the JQL result rows on stdin, prints channel-tagged blocks,
                records the emitted keys as sent

Field mapping (verified against OPD-3):
    summary                     -> summary
    designer                    -> customfield_12707  (Product Owner)
    pod (routing)               -> customfield_13434  (Pod)
    figma link(s)               -> customfield_12714  (Design)
    completed_on                -> customfield_13239  (Actual Design/Research Finish Date),
                                   falling back to statuscategorychangedate (went Done)
"""
import json
from collections import OrderedDict
from datetime import datetime

from core import protocol, gitstate

PROJECT = "OPD"
RECENCY_DAYS = 7
BROWSE = "https://altayerdigital.atlassian.net/browse/%s"
STATE_PATH = "state/design_completed.json"

F_SUMMARY = "summary"
F_DESIGNER = "customfield_12707"
F_POD = "customfield_13434"
F_FIGMA = "customfield_12714"
F_DESIGN_FINISH = "customfield_13239"
F_DONE_TS = "statuscategorychangedate"

QUERY_FIELDS = [F_SUMMARY, F_DESIGNER, F_POD, F_FIGMA, F_DESIGN_FINISH, F_DONE_TS]


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
    """Normalise a raw jira-rest issue into the fields we display + route on."""
    f = issue.get("fields", {}) or {}

    owners = f.get(F_DESIGNER) or []
    designer = ", ".join(o.get("displayName", "") for o in owners if o.get("displayName"))

    pods = f.get(F_POD) or []
    pod = pods[0] if pods else None

    figma = [(d.get("displayName") or d.get("url"), d.get("url"))
             for d in (f.get(F_FIGMA) or []) if d.get("url")]

    completed_on = _fmt_date(f.get(F_DESIGN_FINISH)) or _fmt_date(f.get(F_DONE_TS))

    return {
        "key": issue.get("key"),
        "summary": f.get(F_SUMMARY) or "",
        "designer": designer,
        "pod": pod,
        "figma": figma,
        "completed_on": completed_on,
    }


def _slack_link(url, label):
    return "<%s|%s>" % (url, label)


def _ticket_lines(t):
    """One ticket -> a list of Slack mrkdwn lines."""
    key = t["key"]
    lines = ["• %s — %s" % (_slack_link(BROWSE % key, key), t["summary"])]
    meta = []
    if t["designer"]:
        meta.append("👤 %s" % t["designer"])
    if t["completed_on"]:
        meta.append("📅 %s" % t["completed_on"])
    if meta:
        lines.append("   " + " · ".join(meta))
    for label, url in t["figma"]:
        lines.append("   🔗 %s" % _slack_link(url, label))
    if not t["figma"]:
        lines.append("   🔗 _no Figma link on ticket_")
    return lines


def format_body(pod, tickets):
    """Render a channel's block body: a POD header + each ticket."""
    header = "🎨 *Design completed* — %s" % (pod if pod else "_no POD set_")
    lines = [header]
    for t in tickets:
        lines.extend(_ticket_lines(t))
    return "\n".join(lines)


def channel_for(pod, pod_channels, fallback):
    return pod_channels.get(pod, fallback) if pod else fallback


def render(issues, sent_keys, pod_channels, fallback):
    """Filter already-sent tickets, group new ones by POD, and return
    (channel-tagged output string, list of newly-emitted keys)."""
    new = [extract_ticket(i) for i in issues if i.get("key") not in sent_keys]

    by_pod = OrderedDict()
    for t in new:
        by_pod.setdefault(t["pod"], []).append(t)

    blocks = [(channel_for(pod, pod_channels, fallback), format_body(pod, tickets))
              for pod, tickets in by_pod.items()]

    new_keys = [t["key"] for t in new]
    return protocol.render_blocks(blocks), new_keys


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


def run(sub, stdin_text="", state_path=STATE_PATH, pod_channels=None, fallback=None):
    """Entry point invoked by pm.py. `sub` is 'query' or 'render'. Returns the string to
    print (empty string = print nothing)."""
    if sub == "query":
        return json.dumps(build_query(), indent=2)

    if sub == "render":
        if pod_channels is None or fallback is None:
            import config
            pod_channels = config.POD_CHANNELS if pod_channels is None else pod_channels
            fallback = config.FALLBACK_CHANNEL if fallback is None else fallback

        issues = coerce_issues(json.loads(stdin_text)) if stdin_text.strip() else []
        first_run = not gitstate.state_exists(state_path)
        sent = gitstate.load_sent(state_path)

        out, new_keys = render(issues, sent, pod_channels, fallback)
        final_out, record = select_output(out, new_keys, first_run)

        if record:
            gitstate.save_sent(state_path, sent | set(record),
                               "chore(design-completed): record %d sent" % len(record))
        return final_out

    raise ValueError("unknown subcommand: %s (expected 'query' or 'render')" % sub)
