"""Canonical, versioned artifact encoding used only by the benchmark harness."""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


def canonical(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def write_json(path: Path, value: object) -> None:
    """Create once; never silently overwrite historical evidence."""
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
