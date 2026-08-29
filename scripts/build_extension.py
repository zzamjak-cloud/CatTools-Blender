#!/usr/bin/env python3
"""CatTools Blender Extension 설치 패키지를 생성합니다."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES = (
    "__init__.py",
    "blender_manifest.toml",
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CatTools 설치 ZIP 생성")
    parser.add_argument("--output", type=Path, help="출력 ZIP 경로")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = tomllib.loads((ROOT / "blender_manifest.toml").read_text(encoding="utf-8"))
    output = args.output or ROOT / "dist" / f"cat_tools-v{manifest['version']}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in PACKAGE_FILES:
            archive.write(ROOT / relative_path, relative_path)

    print(output)


if __name__ == "__main__":
    main()
