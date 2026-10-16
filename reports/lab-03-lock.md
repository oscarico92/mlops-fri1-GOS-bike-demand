# Lab 3, lock area: a missing or stale `uv.lock` must stop the install

Owner: Gautier Deplanque (`gautierdpl`). Part of the Lab 3 team record; other areas (Dockerfile, rerun,
README) are recorded by their owners.

## Rule

Dependencies come only from the committed `uv.lock`. Every install uses `--locked`, which fails when the
lock is missing or does not match `pyproject.toml`. `--frozen` is not used: it skips that check, so it is not
a repair. The lock is never regenerated to get a green result.

## What this PR changes

- CI: new first step `uv lock --check`, named so a stale or missing lock shows up as its own failed check
  instead of a generic sync error.
- `.gitattributes`: `uv.lock -text`. Before this, Git on Windows (`core.autocrlf`) rewrote the lock with CRLF
  line endings, so the same committed lock (blob `8478e0e`) had SHA-256 `8d841200…` on Windows and
  `8598f1f2…` on Linux. uv accepted both, but the checksum could not identify the build. The lock is now
  byte-identical on every OS and in the image.
  `.gitattributes` only applies when the file is written again: an existing Windows clone keeps its CRLF
  lock, and after pulling this change `git status` shows `uv.lock` as modified. Fix once per clone, without
  touching the committed lock: `Remove-Item uv.lock; git checkout -- uv.lock` (macOS/Linux:
  `rm uv.lock && git checkout -- uv.lock`). `git rm --cached uv.lock && git checkout -- uv.lock` does not work:
  the checkout fails with "pathspec did not match" and leaves the lock staged for deletion.
- `scripts/lock_check_demo.py`: reruns the demonstration on throwaway copies of the committed tree
  (`git archive HEAD`); the repository and its `uv.lock` are never modified. Any teammate can rerun it:
  `uv run --locked python scripts/lock_check_demo.py`.

## Evidence on my machine

Windows 11 Famille 10.0.26200, uv 0.12.23, commit `296a14d`, clean tree; same results on `deab08d` and on
Simon's macOS rerun (`dc231f1`). Raw log:
[`logs/lab-03/lock-demo.txt`](../logs/lab-03/lock-demo.txt).

| Case | Command | Exit | Message |
| --- | --- | --- | --- |
| committed lock | `uv lock --check` | 0 | — |
| missing lock | `uv lock --check` | 1 | `Unable to find lockfile at uv.lock, but --check was provided` |
| missing lock | `uv sync --locked` | 1 | `Unable to find lockfile at uv.lock, but --locked was provided` |
| stale lock | `uv lock --check` | 1 | `The lockfile at uv.lock needs to be updated, but --check was provided` |
| stale lock | `uv sync --locked` | 1 | `The lockfile at uv.lock needs to be updated, but --locked was provided` |
| stale lock | `uv sync --frozen` | **0** | none: the newly declared `httpx` is not installed |

- No copy regenerated a lock; the stale copy's `uv.lock` and the repository's `uv.lock` kept SHA-256
  `8598f1f2…` (same value on Linux since the `.gitattributes` change).
- The `--frozen` row is why installs use `--locked`: `--frozen` exits 0 while the environment no longer
  matches `pyproject.toml`.
- The script also fails if the `--frozen` environment unexpectedly contains `httpx`.
- The stale case adds `httpx==0.28.1` to `dependencies` in a copy of `pyproject.toml` without running `uv lock`.

## In the container

Recorded by Simon in the Dockerfile PR: on a stale-lock copy, `docker build` stops at the `uv sync --locked`
step with "The lockfile at `uv.lock` needs to be updated". Log: `logs/lab-03/stale-lock.log` (link to be
checked once that PR is merged).
