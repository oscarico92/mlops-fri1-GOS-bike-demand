"""Show that a missing or stale uv.lock stops the install (Lab 3, lock area).

Works on a throwaway copy of the committed tree (``git archive HEAD``): the
repository is never modified and ``uv.lock`` is never regenerated. Run it from
the project root:

    uv run --locked python scripts/lock_check_demo.py

Exit code 0 means every case behaved as expected.
"""

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

MISSING = "Unable to find lockfile"
STALE = "needs to be updated"
STALE_DEPENDENCY = '    "httpx==0.28.1",'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


UV = os.environ.get("UV", "uv")  # `uv run` exports the path of the running uv


def uv(args: list[str], cwd: Path) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    result = subprocess.run(
        [UV, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    lines = [line for line in result.stderr.splitlines() if line.startswith("error")]
    return result.returncode, lines[0] if lines else "(no error)"


def checkout_copy(destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")


def make_stale(project: Path) -> None:
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if "dependencies = [\n" not in text:
        raise SystemExit("pyproject.toml: dependencies list not found")
    pyproject.write_text(
        text.replace(
            "dependencies = [\n", f"dependencies = [\n{STALE_DEPENDENCY}\n", 1
        ),
        encoding="utf-8",
    )


def main() -> int:
    failures = 0

    def expect(label: str, args: list[str], cwd: Path, reason: str | None) -> None:
        """reason=None: the command must pass; otherwise it must fail with `reason`."""
        nonlocal failures
        code, message = uv(args, cwd)
        ok = code == 0 if reason is None else code != 0 and reason in message
        failures += not ok
        verdict = "as expected" if ok else "UNEXPECTED"
        print(f"[{verdict}] {label}: uv {' '.join(args)} -> exit {code}; {message}")

    with tempfile.TemporaryDirectory(
        prefix="lock-demo-", ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        committed = sha256(Path("uv.lock"))
        print(f"Committed uv.lock sha256: {committed}")

        valid = root / "valid"
        checkout_copy(valid)
        expect("committed lock", ["lock", "--check"], valid, None)

        missing = root / "missing"
        checkout_copy(missing)
        (missing / "uv.lock").unlink()
        expect("missing lock", ["lock", "--check"], missing, MISSING)
        expect("missing lock", ["sync", "--locked"], missing, MISSING)
        regenerated = (missing / "uv.lock").exists()
        failures += regenerated
        print(f"Missing-lock copy regenerated a lock: {regenerated}")

        stale = root / "stale"
        checkout_copy(stale)
        make_stale(stale)
        expect("stale lock", ["lock", "--check"], stale, STALE)
        expect("stale lock", ["sync", "--locked"], stale, STALE)
        expect("stale lock, --frozen (no check)", ["sync", "--frozen"], stale, None)
        code, _ = uv(["run", "--frozen", "python", "-c", "import httpx"], stale)
        print(f"--frozen env has the newly declared httpx: {code == 0}")
        unchanged = sha256(stale / "uv.lock") == committed
        failures += not unchanged
        print(f"Stale-copy uv.lock unchanged after all commands: {unchanged}")

    print(f"Repository uv.lock unchanged: {sha256(Path('uv.lock')) == committed}")
    print("All cases as expected." if failures == 0 else f"{failures} unexpected.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
