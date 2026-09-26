"""Verify the append-only Supabase migration contract without contacting a database."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


SUPABASE_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = SUPABASE_ROOT / "migrations"
MANIFEST = SUPABASE_ROOT / "migration-manifest.json"
MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{14})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")


def main() -> int:
    errors: list[str] = []
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = data.get("migrations")
    if data.get("format") != 1 or not isinstance(entries, list):
        raise SystemExit("migration manifest format is invalid")

    actual_files = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
    manifest_files = [entry.get("file") for entry in entries]
    if manifest_files != actual_files:
        errors.append("manifest files must exactly match sorted migration files")

    versions: list[str] = []
    for entry in entries:
        filename = entry.get("file")
        if not isinstance(filename, str):
            errors.append("manifest contains a non-string filename")
            continue
        match = MIGRATION_NAME.fullmatch(filename)
        if match is None:
            errors.append(f"invalid migration filename: {filename}")
            continue
        version = match.group("version")
        versions.append(version)
        if entry.get("version") != version:
            errors.append(f"manifest version differs from filename: {filename}")

        path = MIGRATIONS / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if entry.get("sha256") != digest:
            errors.append(f"migration hash differs from manifest: {filename}")

        sql = path.read_text(encoding="utf-8")
        if f"values ('{version}'," not in sql.lower():
            errors.append(f"migration does not register its contract version: {filename}")
        if re.search(r"\b(drop\s+schema|drop\s+table)\b", sql, re.IGNORECASE):
            errors.append(f"destructive DDL requires a reviewed forward-repair exception: {filename}")

    if versions != sorted(set(versions)):
        errors.append("migration versions must be unique and strictly ordered")

    config = (SUPABASE_ROOT / "config.toml").read_text(encoding="utf-8")
    exposed = re.search(r"(?m)^schemas\s*=\s*\[(?P<schemas>[^]]*)\]", config)
    if exposed is None or re.search(r"[\"']app[\"']", exposed.group("schemas")):
        errors.append("app schema must be absent from Data API exposed schemas")

    if errors:
        print("Supabase migration contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Supabase migration contract passed ({len(entries)} immutable files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
