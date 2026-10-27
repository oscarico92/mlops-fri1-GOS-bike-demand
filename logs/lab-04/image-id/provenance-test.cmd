@echo off
rem Does the image ID stay the same across two cached builds without the provenance attestation?
cd /d C:\dev\mlops-fri1-GOS-bike-demand
set O=C:\dev\provenance-test.txt
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
