#!/usr/bin/env python3
"""Blender Extension 저장소 인덱스에서 애드온별 최신 버전만 남깁니다."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_PART_RE = re.compile(r"(\d+|[A-Za-z]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extension 저장소 index.json 정규화")
    parser.add_argument("index_path", type=Path, help="정렬할 index.json 경로")
    return parser.parse_args()


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    parts: list[tuple[int, int | str]] = []
    for part in VERSION_PART_RE.findall(version):
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part.lower()))
    return tuple(parts)


def sort_index(index_path: Path) -> None:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    latest_by_id: dict[str, dict] = {}
    for item in data.get("data", []):
        addon_id = item.get("id", "")
        current = latest_by_id.get(addon_id)
        if current is None or version_key(item.get("version", "0")) > version_key(
            current.get("version", "0")
        ):
            latest_by_id[addon_id] = item

    data["data"] = [latest_by_id[addon_id] for addon_id in sorted(latest_by_id)]
    index_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    sort_index(args.index_path)


if __name__ == "__main__":
    main()
