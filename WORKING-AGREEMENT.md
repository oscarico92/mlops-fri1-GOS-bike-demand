# Team working agreement

- Team and repository (`mlops-<session>-<team-name>-bike-demand`): GOS, `mlops-fri1-GOS-bike-demand` (to be renamed `mlops-fri1-gos-bike-demand`)
- Members: Oscar Schwartz (`oscarico92`), Gautier Deplanque (`gautierdpl`), Simon Gallais (`Urazikk`)
- Current driver / reviewer / evidence recorder: Lab 1: Oscar / Gautier / Oscar. Lab 2: Gautier / Oscar / Simon
- Fourth member's temporary responsibility, if applicable: n/a, team of 3

## Workflow

- Keep each change small and work on a task branch.
- Open a pull request; a different member reviews the diff before merge.
- Record one actionable observation and the author's response.
- Run the relevant local checks and inspect CI on the latest pushed revision.
- Never commit `.venv`, artifacts, tracking databases, credentials or private reports.
- Rotate substantive work; acknowledge supplied code and other assistance.
- No direct pushes to `main`: every change, including docs, goes through a PR.
- Merge only after the reviewer approves and CI is green on the latest commit; the author merges after approval.

## Support and handover

- Approved support route / supported workstation: team group chat first, then the instructor (minhtc-uca, minhtc.uca@gmail.com) if setup is blocked for more than five minutes. Workstations: Oscar: Windows 11; Gautier: Windows 11 Home; Simon: macOS.
- How to report a setup or repository-access blocker: message in the team chat with the command, full error output and OS; record it in the lab worksheet.
- Next driver and unfinished work: Lab 2 lead Gautier Deplanque; Lab 2 TODOs in `validate.py`, `split.py`, `train.py`.
