#!/usr/bin/env python3
"""Product master routines — one script backing a family of Claude routines.

Each use case is one mode; each mode maps to one routine. Use cases are isolated: adding
one is a new module in usecases/ + one line in USE_CASES below, and never touches another.

    python3 pm.py <use-case> <subcommand>

The script owns all business logic (query, dedup, routing, formatting). The routine prompt
only runs the query the script emits (via a connector) and posts the blocks it prints (to
Slack). stdout is the message; empty stdout means do nothing.

design-completed:
    python3 pm.py design-completed query    -> prints {"jql", "fields"} to run via jira-rest
    python3 pm.py design-completed render     -> reads JQL rows (JSON) on stdin, prints
                                               channel-tagged Slack blocks, records sent keys
"""
import sys

from usecases import design_completed

USE_CASES = {
    "design-completed": design_completed.run,
}


def dispatch(argv, stdin_text=""):
    """Route argv to a use case. Returns (output, exit_code). Pure enough to test."""
    if not argv or argv[0] not in USE_CASES:
        avail = ", ".join(sorted(USE_CASES))
        return ("usage: pm.py <use-case> <subcommand>\navailable use cases: %s" % avail, 2)
    handler = argv[0]
    sub = argv[1] if len(argv) > 1 else "render"
    try:
        out = USE_CASES[handler](sub, stdin_text)
    except Exception as e:
        return ("error in %s %s: %s" % (handler, sub, e), 1)
    return (out or "", 0)


def main():
    argv = sys.argv[1:]
    sub = argv[1] if len(argv) > 1 else "render"
    # Only the render subcommand consumes stdin (the JQL result rows).
    stdin_text = sys.stdin.read() if sub == "render" and not sys.stdin.isatty() else ""
    out, code = dispatch(argv, stdin_text)
    if out:
        stream = sys.stdout if code == 0 else sys.stderr
        print(out, file=stream)
    sys.exit(code)


if __name__ == "__main__":
    main()
