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
- `scripts/lock_check_demo.py`: reruns the demonstration on throwaway copies of the committed tree
  (`git archive HEAD`); the repository and its `uv.lock` are never modified. Any teammate can rerun it:
  `uv run --locked python scripts/lock_check_demo.py`.

## Evidence on my machine

_(Windows 11 Famille, uv 0.12.23, commit `<sha>`: paste the script output.)_

## In the container

_(After the Dockerfile PR is merged: the same stale-lock copy must make `docker build` stop at the
`uv sync --locked` step. Paste the failing step and message.)_
