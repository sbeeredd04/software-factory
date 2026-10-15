# Architecture

`format_payload` is a pure validation/formatting boundary. `Handler` maps HTTP input and output; `--once` exposes the same contract without a server. Tests cover both function and a bounded owned loopback server.
