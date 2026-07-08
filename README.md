# product-master-routines

One master script (`pm.py`) backing a **family** of Claude routines for product management.
Each use case is one mode of the script and maps to one routine. Use cases are isolated —
adding one never touches another — so they stay clearly differentiated and cannot conflict.

Modeled on the `ounass_slots.py` slot-watch routine: mode dispatch, git-committed state,
**stdout is the message** (empty stdout = do nothing).

## Principle: script = brain, Claude = hands

A routine runs `pm.py` as a subprocess. That subprocess **cannot** call Claude's MCP
connectors and has no injected credentials. So:

- **The script owns all business logic** — the query, the field list, dedup, routing, formatting.
- **Claude does only the I/O the subprocess can't reach** — run the query the script emits
  (via a connector) and post the blocks it prints (to Slack).

The routine prompt contains no logic, no query, no channel IDs.

## Layout

```
pm.py                       # entry point + dispatcher (USE_CASES registry)
usecases/design_completed.py# use case #1
core/protocol.py            # channel-tagged block format (shared)
core/gitstate.py            # git-committed state (shared)
config.py                   # POD -> Slack channel map + fallback
state/design_completed.json # created on first run (git-committed dedup)
tests/                      # unittest (stdlib, no pip installs)
docs/specs/                 # design spec
```

## Adding a use case

1. Add `usecases/<name>.py` exposing `run(sub, stdin_text, ...)`.
2. Register it: `USE_CASES = {"<name>": <module>.run, ...}` in `pm.py`.
3. Create a routine pointing at it (below). Existing use cases are untouched.

## Use case: `design-completed`

Alerts a Slack channel (mapped by the ticket's POD) when an OPD design ticket reaches Done —
once per ticket.

```
python3 pm.py design-completed query    # prints {"jql", "fields"} to run via jira-rest
python3 pm.py design-completed render     # reads JQL rows (JSON) on stdin, prints
                                         # channel-tagged Slack blocks, records sent keys
```

- **Dedup:** `state/design_completed.json` (git-committed), fail-open. At most one alert per key.
- **Cold-start:** first run with no state file records all current keys silently (no backlog blast).
- **Routing:** `config.py` maps POD -> Slack channel; unmapped/blank POD -> `FALLBACK_CHANNEL`
  (currently Dinesh's DM `D04LBFPJEMT` during the test phase). Every value is a plain Slack
  target the prompt posts to directly — no special-casing.

### Routine setup

- **Repo:** this repo. **Connectors:** jira-rest (or jiraanalysis) + Slack. **Schedule:** e.g. hourly.
- **Prompt:**

```
1. Run from repo root: python3 pm.py design-completed query
   Parse stdout as JSON {jql, fields}. Run that JQL via the jira connector, requesting those fields.
2. Pipe the resulting issues as JSON into: python3 pm.py design-completed render
3. The script prints zero or more blocks. Each block starts with a line "==channel=<target>=="
   followed by a body. For each block, post the body text VERBATIM to the Slack channel
   identified by <target> (a channel id, channel name, or DM id). If there are no blocks, do nothing.
```

## Tests

```
python3 -m unittest discover -s tests
```
