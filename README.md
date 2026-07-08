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

Prints one Slack message listing OPD design tickets that have reached Done — once per ticket.
The routine posts that message to a single channel it names in its prompt.

```
python3 pm.py design-completed query    # prints {"jql", "fields"} to run via jira-rest
python3 pm.py design-completed render     # reads JQL rows (JSON) on stdin, prints the
                                         # Slack message, records sent keys
```

- **Dedup:** `state/design_completed.json` (git-committed), fail-open. At most one alert per key.
- **Cold-start:** first run with no state file records all current keys silently (no backlog blast).
- **Fields:** summary · designer (Product Owner) · completed-on · Figma link(s), rendered as
  standard-markdown links (the format the Slack connector expects).

### Routine setup

- **Repo:** this repo. **Connectors:** jira-rest (or jiraanalysis) + Slack. **Schedule:** e.g. hourly.
- **Prompt** (replace `<CHANNEL>` with your channel name/id or a person):

```
1. From the repo root, run: python3 pm.py design-completed query
   Parse stdout as JSON { "jql", "fields" }. Run that JQL via the jira-rest connector,
   requesting exactly those fields.
2. Pipe the resulting issues as JSON into stdin of:
   python3 pm.py design-completed render
3. If the script prints anything, post it VERBATIM (do not reformat) to <CHANNEL>.
   If it prints nothing, do nothing.
```

## Tests

```
python3 -m unittest discover -s tests
```
