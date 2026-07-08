"""Channel-tagged block format, shared by every use case.

A use case prints zero or more blocks to stdout. Each block is a header line
`==channel=<channel>==` followed by the message body. The routine prompt reads the
header and posts the body verbatim to that Slack channel. Blocks are separated by a
blank line for readability; the header line is what the routine keys on.
"""

HEADER = "==channel=%s=="


def render_blocks(blocks):
    """blocks: iterable of (channel, body) pairs. Returns the tagged string
    (empty string when there are no blocks)."""
    parts = []
    for channel, body in blocks:
        parts.append("%s\n%s" % (HEADER % channel, body))
    return "\n\n".join(parts)
