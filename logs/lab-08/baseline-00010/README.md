# Lab 8 second baseline on the incident revision (Simon, operator)

Merging #33-#36 on 10 November redeployed the service, so the first baseline (00009, 6e97194) was no longer the
live revision. This second, short baseline uses the same workload and definitions on the revision that is live for
the incident: main c2fc401 (/health code_revision c2fc401..., model d24c050e..., model_version baseline-637fa42462b2).

- Workload: run 1923194c8c, 40 valid + 10 invalid, 2026-11-10 19:23:19-19:23:24 UTC; client 40 x 200, 10 x 422.
- Logs read with a timestamp window 19:22:30-19:25:00 (cloud-logs.json, remoteIp redacted).
- Signals (signals.txt): 50/50 logged, missing 0, success 1.0, 10 intentional rejections, 0 invalid accepted,
  latency p50 12.0 ms, p95 13.8 ms, max 14.1 ms, one identity.
