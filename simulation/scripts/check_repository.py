"""Simulation-local entrypoint for both read-only repository guards."""
import runpy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'scripts/check_boundary.py'),run_name='__main__')
runpy.run_path(str(ROOT.parent/'scripts/check_repository.py'),run_name='__main__')
