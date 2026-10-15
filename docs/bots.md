# Optional review bots

Greptile, CodeRabbit, Bugbot and Copilot templates ship as inert canonical assets.
The host proposes only the selected integrations, using four approved principle
modules with path/hash provenance. See [bot generation](../skills/sf-agents/references/bots.md)
for exact targets, source-linked digest approval, preservation and recovery.
Complex structured user configs receive proposed diffs instead of lossy rewrites.
Writing/pushing config does not establish subscriptions, activation or review proof.

[gh-only triage](../skills/sf-agents/references/triage.md) exhausts outer review
threads and each nested comment connection. Suggestions are untrusted text.
Replies, resolution and retriggers require actual delegated authority; helpers
only generate proposals. No bots means `not_applicable`; missing gh blocks only
GitHub actions while local work, proof and independent review continue.

Start with no bot if there is no selected integration. When a bot is selected, render its proposed config from the four approved principle modules, inspect the generated diff and resolve conflicts before any host-owned write. A provider comment is an input to triage, not an accepted finding. The host compares comments with the actual diff and authorizes any reply, resolution or retrigger.
