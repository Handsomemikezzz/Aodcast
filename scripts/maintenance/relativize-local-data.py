#!/usr/bin/env python3
"""One-off repair: rewrite absolute file paths stored in .local-data JSON to data-dir-relative paths.

Run it after moving a checkout (or upgrading from a version that stored absolute paths).
Dry-run by default; pass --apply to write. Changed files are copied to a timestamped
backup directory inside the data dir first. Only sessions/** and speaker-references/**
JSON files are touched.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR_PATH = re.compile(r'"/[^"\n]*?/\.local-data/([^"\n]*)"')
BUILTIN_ASSET_PATH = re.compile(r'"/[^"\n]*?/app/assets/speaker-references/([^"\n]*)"')
SCAN_DIRS = ("sessions", "speaker-references")


def rewrite(text: str) -> tuple[str, list[str]]:
    """Return the rewritten text and the stored (relative) targets it now contains."""
    targets: list[str] = []

    def to_relative(match: re.Match[str]) -> str:
        targets.append(match.group(1))
        return f'"{match.group(1)}"'

    def to_builtin(match: re.Match[str]) -> str:
        return f'"builtin:{match.group(1)}"'

    text = DATA_DIR_PATH.sub(to_relative, text)
    text = BUILTIN_ASSET_PATH.sub(to_builtin, text)
    return text, targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True, type=Path, help="Path to the .local-data directory.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run).")
    args = parser.parse_args()

    data_dir = args.data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        print(f"Data dir not found: {data_dir}", file=sys.stderr)
        return 2

    backup_dir = data_dir / f"relativize-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    files_changed = 0
    paths_rewritten = 0
    missing: list[str] = []

    for name in SCAN_DIRS:
        for path in sorted((data_dir / name).rglob("*.json")):
            original = path.read_text(encoding="utf-8")
            updated, targets = rewrite(original)
            if updated == original:
                continue
            json.loads(updated)  # never write a file that stopped being valid JSON
            files_changed += 1
            paths_rewritten += len(DATA_DIR_PATH.findall(original)) + len(BUILTIN_ASSET_PATH.findall(original))
            missing.extend(sorted({t for t in targets if not (data_dir / t).exists()}))
            if args.apply:
                backup = backup_dir / path.relative_to(data_dir)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                path.write_text(updated, encoding="utf-8")

    mode = "applied" if args.apply else "dry run (use --apply to write)"
    print(f"Mode: {mode}")
    print(f"Files changed: {files_changed}")
    print(f"Paths rewritten: {paths_rewritten}")
    print(f"Rewritten targets that do not exist: {len(set(missing))}")
    for target in sorted(set(missing)):
        print(f"  missing: {target}")
    if args.apply and files_changed:
        print(f"Backup: {backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
