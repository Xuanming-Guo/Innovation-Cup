"""Read-only guard for the simulation-only implementation boundary."""

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Historical starting point retained for provenance and older test doubles. The
# guard intentionally does not require HEAD to remain frozen after reviewed
# implementation commits are created.
EXPECTED_HEAD = "d0bf6fe30b48aab20047f4b254b97f4d6195a5bb"
EXPECTED_BRANCH = "feat/13-simulation"
IMMUTABLE = {
    "simulation_implementation_prompt.md": "efd849f8e7064a2da3f91c43de17ad6ece6e999a57617f1ee246dc562fe7a8e8",
    "coordination_engine_simulation_context_v2.docx": "7fb753efa9a798855d3e5c56fa85e2e468cadff7139b47b8609be2e82dc72eae",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=ROOT, text=True)


def check() -> list[str]:
    errors = []
    if git("branch", "--show-current").strip() != EXPECTED_BRANCH:
        errors.append("branch changed from bootstrap baseline")
    if git("diff", "--cached", "--name-only"):
        errors.append("index differs from clean baseline")
    records = git("status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    # Renames/copies are outside this bootstrap; deny instead of misparsing two-path records.
    for row in filter(None, records):
        if row[0] in "RC" or row[1] in "RC" or not row[3:].startswith("simulation/"):
            errors.append("repository change outside allowed simulation additions/edits")
    for name, expected in IMMUTABLE.items():
        if not (ROOT / name).exists() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            errors.append(f"immutable control input changed: {name}")
    for name in (".venv", ".cache", ".tmp", "runs"):
        if not (ROOT / name).resolve().is_relative_to(ROOT):
            errors.append(f"local runtime path escapes simulation: {name}")
    return errors


if __name__ == "__main__":
    failures = check()
    if failures:
        raise SystemExit("Boundary check failed: " + "; ".join(failures))
    print("Boundary checks passed: worktree changes stay under simulation/; branch, index and immutable source inputs are valid.")
