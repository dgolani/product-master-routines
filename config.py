"""Routing config for the design-completed use case.

Test phase: POD_CHANNELS is empty, so every alert routes to FALLBACK_CHANNEL, which the
routine prompt resolves to a Slack DM to Dinesh Golani. When ready, fill POD_CHANNELS with
real Slack channel ids — nothing else needs to change.
"""

# POD value (from customfield_13434, e.g. "pod_vm") -> Slack channel id (e.g. "C0ABCDEF").
POD_CHANNELS = {
    # "pod_vm": "C0XXXXXXX",
    # "pod_search": "C0YYYYYYY",
}

# Where tickets with an unmapped or blank POD go.
FALLBACK_CHANNEL = "DINESH_DM"
