"""Blender 안에서 격리 개발 프로필과 CatTools 로드를 검사합니다."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy


MODULE_NAME = "bl_ext.user_default.cat_tools"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    profile_base = Path(os.environ["CATTOOLS_DEV_PROFILE_BASE"]).resolve()
    blender_version = os.environ["BLENDER_VERSION"]
    expected_profile = profile_base / blender_version
    default_profile = (
        Path.home() / "Library" / "Application Support" / "Blender" / blender_version
    )
    addon_link = profile / "extensions" / "user_default" / "cat_tools"

    assert profile == expected_profile, (
        f"격리 프로필 경로가 다릅니다: {profile} != {expected_profile}"
    )
    assert profile != default_profile, (
        f"기본 Blender 프로필을 개발 프로필로 사용하고 있습니다: {profile}"
    )
    assert Path(bpy.utils.resource_path("USER")).resolve() == profile, (
        f"Blender 사용자 리소스 경로가 격리되지 않았습니다: "
        f"{bpy.utils.resource_path('USER')}"
    )
    assert addon_link.is_symlink(), f"개발 확장 심링크가 없습니다: {addon_link}"
    assert addon_link.resolve() == ROOT, (
        f"개발 확장 심링크 대상이 다릅니다: {addon_link.resolve()}"
    )
    assert MODULE_NAME in bpy.context.preferences.addons, (
        f"개발 확장이 활성화되지 않았습니다: {MODULE_NAME}"
    )
    assert not any(
        "woody" in module_name.lower()
        for module_name in bpy.context.preferences.addons.keys()
    ), "격리 개발 프로필에 기존 Woody Tools가 함께 활성화되어 있습니다."

    module = importlib.import_module(MODULE_NAME)
    assert Path(module.__file__).resolve() == ROOT / "__init__.py", (
        f"저장소 소스가 아닌 확장이 로드되었습니다: {module.__file__}"
    )
    print(f"CatTools 격리 개발 프로필 스모크 테스트 통과: {profile}")


if __name__ == "__main__":
    main()
