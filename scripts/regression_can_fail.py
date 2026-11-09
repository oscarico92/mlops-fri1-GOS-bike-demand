"""Show that each regression test fails for the defect it names (Lab 6).

For each defect: copy the working tree to a throwaway folder, inject one believable
defect, run `pytest -m regression` there and check that the named test fails. The
repository itself is never modified. Exit 1 if the clean copy is not green or if a
defect is not caught.

    uv run --locked python scripts/regression_can_fail.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = "tests/regression/test_recorded_baseline.py"


def edit(path: str, old: str, new: str):
    def apply(copy: Path) -> None:
        target = copy / path
        text = target.read_text()
        if text.count(old) != 1:
            raise SystemExit(f"defect setup: {old!r} not found once in {path}")
        target.write_text(text.replace(old, new))

    return apply


def edit_data(copy: Path) -> None:
    """Change the label of one validation hour by one rental."""
    target = copy / "data/raw/hour.csv"
    lines = target.read_text().splitlines(keepends=True)
    for index, line in enumerate(lines):
        if ",2012-03-15," in line:
            fields = line.rstrip("\n").split(",")
            fields[-1] = str(int(fields[-1]) + 1)
            lines[index] = ",".join(fields) + "\n"
            break
    target.write_text("".join(lines))


def both(*steps):
    def apply(copy: Path) -> None:
        for step in steps:
            step(copy)

    return apply


DEFECTS = [
    (
        "raw data edited (one validation label +1)",
        edit_data,
        "test_frozen_data_is_the_recorded_snapshot",
    ),
    (
        "validation window ends one day early (2012-06-30 moves to test)",
        both(
            edit(
                "src/bike_demand/split.py",
                '("2012-01-01", "2012-06-30")',
                '("2012-01-01", "2012-06-29")',
            ),
            edit(
                "src/bike_demand/split.py",
                '("2012-07-01", "2012-12-31")',
                '("2012-06-30", "2012-12-31")',
            ),
        ),
        "test_partitions_match_the_recorded_split",
    ),
    (
        "comparator uses validation labels (leakage)",
        edit(
            "src/bike_demand/train.py",
            "mean = float(train_target.mean())",
            "mean = float(validation_target.mean())",
        ),
        "test_train_mean_comparator_recomputes",
    ),
    (
        "model setting changed without review (max_depth 10 -> 11, preset and config)",
        both(
            edit("src/bike_demand/train.py", '"max_depth": 10', '"max_depth": 11'),
            edit("configs/baseline.yaml", "max_depth: 10", "max_depth: 11"),
        ),
        "test_random_forest_validation_mae_recomputes",
    ),
    (
        "API rescales an input (humidity sent to the model as a percentage)",
        edit(
            "src/bike_demand/api.py",
            "    row = pd.DataFrame([request.model_dump()], columns=list(FEATURES))\n",
            "    row = pd.DataFrame([request.model_dump()], columns=list(FEATURES))\n"
            '    row["hum"] = row["hum"] * 100\n',
        ),
        "test_served_prediction_for_the_reference_request",
    ),
]


def copy_tree(destination: Path) -> None:
    files = (
        subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    for name in filter(None, files):
        source = ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def run_tests(copy: Path) -> tuple[int, list[str], str]:
    env = {**os.environ, "PYTHONPATH": str(copy / "src")}
    where = subprocess.run(
        [sys.executable, "-c", "import bike_demand; print(bike_demand.__file__)"],
        cwd=copy,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not Path(where).resolve().is_relative_to(copy.resolve()):
        raise SystemExit(f"setup: tests would import {where}, not the copy")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "regression",
            "-p",
            "no:cacheprovider",
            TEST,
        ],
        cwd=copy,
        env=env,
        capture_output=True,
        text=True,
    )
    failed = sorted(set(re.findall(r"^FAILED \S+::(\w+)", result.stdout, re.MULTILINE)))
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return result.returncode, failed, summary


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean"
        copy_tree(clean)
        code, failed, summary = run_tests(clean)
        green = code == 0 and not failed
        print(
            f"[{'as expected' if green else 'UNEXPECTED'}] no defect: exit {code}; {summary}"
        )
        ok &= green
        for index, (name, inject, expected) in enumerate(DEFECTS, start=1):
            copy = Path(tmp) / f"defect-{index}"
            copy_tree(copy)
            inject(copy)
            code, failed, summary = run_tests(copy)
            caught = code != 0 and expected in failed
            print(f"[{'caught' if caught else 'NOT CAUGHT'}] {name}")
            print(f"    expected red: {expected}")
            print(f"    exit {code}; failed: {', '.join(failed) or 'none'}")
            ok &= caught
    print("All defects caught." if ok else "Some defect was not caught.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
