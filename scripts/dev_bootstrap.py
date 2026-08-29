"""격리 개발 프로필에서 CatTools 확장을 활성화하고 설정을 저장합니다."""

from __future__ import annotations

import importlib

import bpy


MODULE_NAME = "bl_ext.user_default.cat_tools"


def main() -> None:
    if MODULE_NAME not in bpy.context.preferences.addons:
        result = bpy.ops.preferences.addon_enable(module=MODULE_NAME)
        if result != {"FINISHED"}:
            raise RuntimeError(f"CatTools 개발 확장 활성화에 실패했습니다: {result}")
        bpy.ops.wm.save_userpref()
        print(f"CatTools 개발 확장 활성화 완료: {MODULE_NAME}")
    else:
        print(f"CatTools 개발 확장 활성화 확인: {MODULE_NAME}")

    importlib.import_module(MODULE_NAME)


if __name__ == "__main__":
    main()
