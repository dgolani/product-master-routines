"""Routing config for the design-completed use case.

Every channel value here is a plain Slack target that the routine posts to directly (a
channel id, channel name, or DM id) — there is no special-casing in the prompt.

Test phase: POD_CHANNELS is empty, so every alert routes to FALLBACK_CHANNEL, currently
Dinesh Golani's DM (D04LBFPJEMT). In production, fill POD_CHANNELS with real channels and
point FALLBACK_CHANNEL at a real channel — nothing else changes.
"""

# POD value (from customfield_13434, e.g. "pod_vm") -> Slack channel (id or name).
POD_CHANNELS = {
    # "pod_vm": "C0XXXXXXX",
    # "pod_search": "#design-search",
}

# Where tickets with an unmapped or blank POD go. Test phase: Dinesh's DM.
FALLBACK_CHANNEL = "D04LBFPJEMT"
