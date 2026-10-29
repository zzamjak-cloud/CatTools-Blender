"""실제 마우스 이벤트로 CatTools Modeling의 Cylinder·Cube 그리기(바닥 드래그 → 높이 → 클릭)를 검사합니다.

사용: blender --factory-startup --enable-event-simulate --python tests/blender_draw_primitive_gui_smoke.py [-- <캡처 폴더>]
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None

spec = importlib.util.spec_from_file_location("cat_tools_draw_primitive_gui", ROOT / "__init__.py")
addon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(addon)
addon.register()

# 사이드바 버튼과 같은 연산자를 실제 이벤트로 실행하도록 임시 단축키를 단다.
keymap = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name="3D View", space_type='VIEW_3D')
for key, shape in (('F5', 'CYLINDER'), ('F6', 'CUBE')):
    keymap.keymap_items.new(addon.VIEW3D_OT_CatDrawPrimitive.bl_idname, key, 'PRESS').properties.shape = shape

results = []
state = {"events": []}


def view():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return window, area, region, area.spaces.active.region_3d


def to_window(world):
    _window, _area, region, rv3d = view()
    co = location_3d_to_region_2d(region, rv3d, Vector(world))
    return int(round(region.x + co.x)), int(round(region.y + co.y))


def check(condition, message):
    results.append(bool(condition))
    print(("OK   " if condition else "FAIL ") + message)


def capture(name):
    if CAPTURE_DIR is None:
        return
    window, area, _region, _rv3d = view()
    with bpy.context.temp_override(window=window, area=area):
        bpy.ops.screen.screenshot_area(filepath=str(CAPTURE_DIR / name))


def move(pos):
    return ('MOUSEMOVE', 'NOTHING', pos)


def draw_sequence(key, start, drag_end, height_end):
    """key로 실행 → start에서 눌러 drag_end까지 끌고 놓기 → height_end로 옮겨 높이 정하기(클릭은 다음 단계)."""
    seq = [move(start), (key, 'PRESS', start), (key, 'RELEASE', start), move(start), ('LEFTMOUSE', 'PRESS', start)]
    for t in (0.25, 0.5, 0.75, 1.0):
        seq.append(move((int(start[0] + (drag_end[0] - start[0]) * t), int(start[1] + (drag_end[1] - start[1]) * t))))
    seq.append(('LEFTMOUSE', 'RELEASE', drag_end))
    for t in (0.25, 0.5, 0.75, 1.0):
        seq.append(move((int(drag_end[0] + (height_end[0] - drag_end[0]) * t),
                         int(drag_end[1] + (height_end[1] - drag_end[1]) * t))))
    return seq


def newest(prefix):
    return max((o for o in bpy.data.objects if o.name.startswith(prefix)), key=lambda o: o.name, default=None)


def step_setup():
    window, _area, _region, rv3d = view()
    window.event_simulate(type='ESC', value='PRESS')
    window.event_simulate(type='ESC', value='RELEASE')
    rv3d.view_rotation = Quaternion((0.82, 0.42, 0.18, 0.35)).normalized()
    rv3d.view_location = (0.0, 0.0, 0.5)
    rv3d.view_distance = 11.0
    for obj in bpy.data.objects:
        obj.select_set(False)


def step_cylinder():
    # 기본 큐브 윗면(z=1) 가운데에서 반지름 0.6으로 그리고, 노멀(+Z) 방향 높이 1.2로 올린다.
    state["events"] = draw_sequence(
        'F5', to_window((0.0, 0.0, 1.0)), to_window((0.6, 0.0, 1.0)), to_window((0.6, 0.0, 2.2))
    )


def step_cylinder_click():
    capture("primitive_cylinder_height.png")
    pos = to_window((0.6, 0.0, 2.2))
    state["events"] = [('LEFTMOUSE', 'PRESS', pos), ('LEFTMOUSE', 'RELEASE', pos)]


def step_cylinder_check():
    obj = newest("Cylinder")
    check(obj is not None and bpy.context.active_object is obj, "실린더 오브젝트 생성·활성화")
    if obj is None:
        return
    z_axis = obj.matrix_world.col[2].xyz
    check((z_axis - Vector((0.0, 0.0, 1.0))).length < 1e-4, f"실린더 축이 윗면 노멀(+Z)을 따름 {tuple(round(c, 3) for c in z_axis)}")
    check((obj.matrix_world.translation - Vector((0.0, 0.0, 1.0))).length < 0.05,
          f"실린더 바닥 중심이 윗면 위 {tuple(round(c, 3) for c in obj.matrix_world.translation)}")
    last = bpy.context.window_manager.operators[-1]
    check(last.bl_idname == "VIEW3D_OT_cat_draw_primitive", f"마지막 연산자 {last.bl_idname}")
    props = last.properties
    check(abs(props.radius - 0.6) < 0.05 and abs(props.height - 1.2) < 0.08,
          f"반지름 {props.radius:.3f} · 높이 {props.height:.3f}")
    check(len(obj.data.vertices) == props.resolution_u * (props.resolution_v + 1), "U·V 해상도대로 정점 생성")
    _window, area, _region, _rv3d = view()
    hud = [r for r in area.regions if r.type == 'HUD' and r.width > 1 and r.height > 1]
    check(bool(hud), "Adjust Last Operation 패널 표시")
    capture("primitive_cylinder_done.png")


def step_cube():
    # 기본 큐브 +X 옆면(x=1) 위에 모서리→모서리로 사각형을 그리고 노멀(+X) 방향 높이 0.8로 민다.
    state["events"] = draw_sequence(
        'F6', to_window((1.0, -0.4, -0.5)), to_window((1.0, 0.5, 0.4)), to_window((1.8, 0.5, 0.4))
    )


def step_cube_click():
    capture("primitive_cube_height.png")
    pos = to_window((1.8, 0.5, 0.4))
    state["events"] = [('LEFTMOUSE', 'PRESS', pos), ('LEFTMOUSE', 'RELEASE', pos)]


def step_cube_check():
    obj = newest("Cube.")
    check(obj is not None and bpy.context.active_object is obj, "큐브 오브젝트 생성·활성화")
    if obj is not None:
        z_axis = obj.matrix_world.col[2].xyz
        check((z_axis - Vector((1.0, 0.0, 0.0))).length < 1e-4, f"큐브 축이 옆면 노멀(+X)을 따름 {tuple(round(c, 3) for c in z_axis)}")
        props = bpy.context.window_manager.operators[-1].properties
        check(abs(props.size_x - 0.9) < 0.06 and abs(props.size_y - 0.9) < 0.06 and abs(props.height - 0.8) < 0.08,
              f"크기 {props.size_x:.3f} x {props.size_y:.3f} · 높이 {props.height:.3f}")
        center = obj.matrix_world.translation
        check(abs(center.x - 1.0) < 1e-3 and abs(center.y - 0.05) < 0.05 and abs(center.z + 0.05) < 0.05,
              f"큐브 바닥 중심이 그린 사각형 중심 {tuple(round(c, 3) for c in center)}")
        capture("primitive_cube_done.png")


def step_cancel():
    # Esc로 취소하면 아무것도 만들지 않고 헤더 안내도 지운다.
    state["count"] = len(bpy.data.objects)
    start = to_window((-0.5, -0.5, 1.0))
    seq = draw_sequence('F5', start, to_window((-0.2, -0.5, 1.0)), to_window((-0.2, -0.5, 1.5)))
    state["events"] = seq + [('ESC', 'PRESS', start), ('ESC', 'RELEASE', start)]


def step_finish():
    check(len(bpy.data.objects) == state["count"], "Esc 취소 시 오브젝트를 만들지 않음")
    print("DRAW PRIMITIVE GUI " + ("PASSED" if all(results) else "FAILED"))
    bpy.ops.wm.quit_blender()


plan = [step_setup, None, step_cylinder, step_cylinder_click, step_cylinder_check, step_cube, step_cube_click,
        step_cube_check, step_cancel, step_finish]


def tick():
    try:
        if state["events"]:
            window = view()[0]
            kind, value, (x, y) = state["events"].pop(0)
            window.event_simulate(type=kind, value=value, x=x, y=y)
            return 0.1
        if not plan:
            return None
        current = plan.pop(0)
        if current is not None:
            current()
        return 0.8
    except Exception:
        import traceback
        traceback.print_exc()
        print("DRAW PRIMITIVE GUI FAILED")
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=2.0)
