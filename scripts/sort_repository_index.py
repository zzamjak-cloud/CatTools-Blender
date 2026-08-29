#!/usr/bin/env python3
"""Blender Extension 저장소 인덱스를 업데이트 판정에 맞게 정렬합니다."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_PART_RE = re.compile(r"(\d+|[A-Za-z]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extension 저장소 index.json 정렬")
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
    data["data"] = sorted(
        data.get("data", []),
        key=lambda item: (item.get("id", ""), version_key(item.get("version", "0"))),
    )
    index_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    sort_index(args.index_path)


if __name__ == "__main__":
    main()
