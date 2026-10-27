@echo off
rem Does the image ID stay the same across two cached builds without the provenance attestation?
rem Run from anywhere: works on the repository that contains this file, writes the result next to it.
rem Recorded run: commit 9b9891c, with the C:\dev paths of the first version of this script.
rem The cause is Docker's attestation, not our code, so the same result is expected on any commit
rem (measured on 9b9891c only).
cd /d "%~dp0..\..\.."
set O="%~dp0provenance-test.txt"
for /f %%c in ('git rev-parse HEAD') do set C=%%c
echo commit %C% > %O%
for %%n in (1 2) do (
  docker build --build-arg GIT_COMMIT=%C% -t prov-default:%%n . > nul 2>&1
  docker build --provenance=false --build-arg GIT_COMMIT=%C% -t prov-off:%%n . > nul 2>&1
)
for %%t in (prov-default:1 prov-default:2 prov-off:1 prov-off:2) do (
  for /f %%i in ('docker image inspect %%t --format "{{.Id}}"') do echo %%t %%i>> %O%
)
type %O%
