"""Blender에서 N 키 사이드바 토글이 CatTools 탭을 활성화하는지 검사합니다.

사이드바 탭 목록은 그리기 단계에서 만들어지므로 GUI 창이 필요하다.
`--background`가 아닌 실제 창에서 실행한다.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"

SHORTCUT_KEY = "N"
SHORTCUT_IDNAME = "view3d.cat_toggle_sidebar"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_sidebar_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def view3d_area():
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            return area
    raise AssertionError("3D 뷰 영역을 찾을 수 없습니다.")


def sidebar_region(area):
    for region in area.regions:
        if region.type == "UI":
            return region
    raise AssertionError("사이드바 영역을 찾을 수 없습니다.")


def toggle_sidebar(area) -> None:
    with bpy.context.temp_override(
        window=bpy.context.window,
        area=area,
        space_data=area.spaces.active,
        region=area.regions[-1],
    ):
        assert bpy.ops.view3d.cat_toggle_sidebar.poll(), "사이드바 토글 연산자를 실행할 수 없습니다."
        result = bpy.ops.view3d.cat_toggle_sidebar()
        assert result == {"FINISHED"}, f"사이드바 토글 결과가 예상과 다릅니다: {result}"


def assert_shortcut_registered(addon) -> None:
    keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View")
    assert keymap is not None, "애드온 키맵에 3D View 항목이 없습니다."
    bindings = [
        (item.idname, item.type)
        for item in keymap.keymap_items
        if item.idname == SHORTCUT_IDNAME
    ]
    assert bindings == [(SHORTCUT_IDNAME, SHORTCUT_KEY)], (
        f"{SHORTCUT_KEY} 키 단축키가 등록되지 않았습니다: {bindings}"
    )
    assert len(addon.addon_keymaps) == 1, (
        f"해제용 키맵 목록이 예상과 다릅니다: {addon.addon_keymaps}"
    )


def main() -> None:
    addon, registered_here = load_addon()
    area = view3d_area()
    space = area.spaces.active
    was_open = space.show_region_ui

    try:
        assert_shortcut_registered(addon)

        # 닫힌 상태에서 시작해 토글이 사이드바를 여는지 확인한다.
        space.show_region_ui = False
        toggle_sidebar(area)
        assert space.show_region_ui, "토글이 사이드바를 열지 못했습니다."

        # 탭 목록은 그리기 이후에 만들어지므로 한 프레임을 강제로 그린다.
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        addon.activate_cat_tab_in_open_sidebars()

        region = sidebar_region(area)
        assert region.active_panel_category == addon.CAT_CATEGORY, (
            f"활성 탭이 {addon.CAT_CATEGORY}가 아닙니다: {region.active_panel_category}"
        )

        # 다른 탭으로 옮긴 뒤 파일 로드 핸들러가 다시 CatTools로 되돌리는지 확인한다.
        region.active_panel_category = "Item"
        addon._on_load_post(None)
        assert region.active_panel_category == addon.CAT_CATEGORY, (
            "load_post 핸들러가 CatTools 탭을 복원하지 못했습니다: "
            f"{region.active_panel_category}"
        )

        # 다시 누르면 닫혀야 한다.
        toggle_sidebar(area)
        assert not space.show_region_ui, "토글이 사이드바를 닫지 못했습니다."
    finally:
        space.show_region_ui = was_open
        if registered_here:
            addon.unregister()
            keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View")
            leftovers = (
                [item.idname for item in keymap.keymap_items if item.idname == SHORTCUT_IDNAME]
                if keymap is not None
                else []
            )
            assert not leftovers, f"해제 후에도 단축키가 남아 있습니다: {leftovers}"
            assert addon._on_load_post not in bpy.app.handlers.load_post, (
                "해제 후에도 load_post 핸들러가 남아 있습니다."
            )

    print("CatTools 사이드바 단축키 Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
    bpy.ops.wm.quit_blender()
