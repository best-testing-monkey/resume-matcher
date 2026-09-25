# benchmark.py
"""Benchmark job_matcher modes against ground truth on resumes/ x jobs/.

Usage:
    python benchmark.py run <mode> [mode ...]   # run sweep(s), then check
    python benchmark.py check <mode>            # check existing results_<mode>.jsonl

Ranking proof: for cv_1000.md and cv_tim_jansen_compact.md, both QA roles
must rank above the Java and Delphi roles, with Delphi last.
Agreement: category verdicts vs ground truth (QA = yes, Delphi = no,
Java = no or maybe accepted as correct).
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

QA_JOBS = {
    "freelance-nl-1183973-test-automation-engineer.md",
    "freelapp-508877-tester-rvo.md",
}
JAVA_JOB = "freelance-nl-1184221-medior-java-developer.md"
DELPHI_JOB = "freelapp-531785-delphi-specialist.md"
LONG_CVS = {"cv_1000.md", "cv_tim_jansen_compact.md"}

CATEGORY_SCORE = {"yes": 1.0, "maybe": 0.5, "no": 0.0}


def results_path(mode: str) -> Path:
    return ROOT / f"results_{mode}.jsonl"


def run_sweep(mode: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "job_matcher.py"),
            "--resumes",
            "resumes/*.md",
            "--jobs",
            "jobs/*.md",
            "--min-strong",
            "0.0",
            "--mode",
            mode,
            "--out",
            str(results_path(mode)),
        ],
        cwd=ROOT,
        check=True,
    )


def load_records(mode: str) -> list[dict]:
    path = results_path(mode)
    if not path.exists():
        sys.exit(f"no results file: {path} (run a sweep first)")
    return [json.loads(line) for line in path.read_text().splitlines()]


def pair_score(mode: str, record: dict) -> float:
    if mode == "rank":
        return record["probs"]["best fit"]
    if mode == "embed":
        return record["probs"]["similarity"]
    if mode == "category":
        return CATEGORY_SCORE[record["top"]]
    return record["probs"]["strong match"]


def check_ranking(mode: str, records: list[dict]) -> bool:
    """Ranking proof on the long CVs: QA roles top, Delphi last."""
    ok = True
    for cv in sorted(LONG_CVS):
        pairs = [
            (Path(r["job_file"]).name, pair_score(mode, r))
            for r in records
            if Path(r["resume_file"]).name == cv
        ]
        if not pairs:
            print(f"  {cv}: no records")
            ok = False
            continue
        pairs.sort(key=lambda x: -x[1])
        ordered = [j for j, _ in pairs]
        top_two = set(ordered[:2])
        qa_top = top_two == QA_JOBS
        delphi_last = ordered[-1] == DELPHI_JOB
        passed = qa_top and delphi_last
        ok = ok and passed
        print(f"  {cv}: {'PASS' if passed else 'FAIL'}")
        for j, s in pairs:
            print(f"    {s:.3f}  {j}")
    return ok


def check_agreement(records: list[dict]) -> None:
    """Category verdicts vs ground truth."""
    agree = total = 0
    for r in records:
        job = Path(r["job_file"]).name
        verdict = r["top"]
        if job in QA_JOBS:
            correct = verdict == "yes"
        elif job == DELPHI_JOB:
            correct = verdict == "no"
        else:
            correct = verdict in {"no", "maybe"}
        agree += correct
        total += 1
    print(f"  agreement: {agree}/{total}")


def check(mode: str) -> bool:
    records = load_records(mode)
    print(f"[{mode}] ranking proof:")
    ok = check_ranking(mode, records)
    if mode == "category":
        print(f"[{mode}] verdict agreement:")
        check_agreement(records)
    return ok


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in {"run", "check"}:
        sys.exit(__doc__)
    action, modes = sys.argv[1], sys.argv[2:]
    results = {}
    for mode in modes:
        if action == "run":
            run_sweep(mode)
        results[mode] = check(mode)
    passed = [m for m, ok in results.items() if ok]
    print()
    if passed:
        print(f"ranking proof PASSED in mode(s): {', '.join(passed)}")
    else:
        print("ranking proof FAILED in all modes tried")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
