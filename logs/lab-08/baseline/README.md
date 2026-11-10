# Lab 8 baseline on Cloud Run (Simon, operator), before any incident

- Revision: the one serving main 6e97194 (/health code_revision 6e97194..., model d24c050e..., model_version baseline-6e8f651c585f); service.json, health.json.
- Workload: run 151807f4a9, 40 valid + 10 invalid, 2026-11-10 15:18:07-15:18:14 UTC; client got 40 x 200 and 10 x 422 (workload.txt, sent.jsonl).
- First read (90 s after the workload, cloud-logs.json): 48/50 lines, missing 2 (valid-15, valid-16), success 0.95 (signals-first-read.txt).
- Two hypotheses: (A) export truncated: rejected, 174 entries for a 2000 limit; (B) lines lost: rejected, a second read limited to 15:17:30-15:19:30 (cloud-logs-window.json) contains both lines; platform request logs show 50 /predict.
- Cause: Cloud Logging ingestion delay; both lines arrived after the first read.
- Baseline (signals.txt, second read): see the file; same definitions as the incident and the recovery.
- Lesson for the incident: a "missing" request is confirmed only by a second read after a few minutes, and checked against the client view and the platform request logs.
- Platform request logs: remoteIp values replaced by "redacted" (personal data); not used by the signals.
