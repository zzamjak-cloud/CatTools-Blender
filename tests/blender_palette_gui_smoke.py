"""실제 창에서 Palette Color 오버레이·호버 미리보기·확정/취소를 이벤트 시뮬레이션으로 검사합니다.

`--enable-event-simulate`가 필요하다:
./scripts/dev_run.sh --enable-event-simulate --python tests/blender_palette_gui_smoke.py
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

import bmesh
import bpy

MODULE_NAME = "bl_ext.user_default.cat_tools"
SHOT = os.path.join(tempfile.gettempdir(), "cat_palette_gui_smoke.png")


def fail(message: str) -> None:
    print(f"CatTools palette GUI smoke: FAIL {message}")
    sys.stdout.flush()
    os._exit(1)


def setup():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")


def face_uvs(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    layer = bm.loops.layers.uv.active
    return [tuple(round(c, 5) for c in loop[layer].uv) for face in bm.faces for loop in face.loops]


def main():
    module = importlib.import_module(MODULE_NAME)
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    obj = bpy.context.object
    original = face_uvs(obj)
    center = (region.x + region.width // 2, region.y + region.height // 2)
    window.event_simulate("MOUSEMOVE", "NOTHING", x=center[0], y=center[1])
    with bpy.context.temp_override(window=window, area=area, region=region):
        result = bpy.ops.mesh.cat_palette_color("INVOKE_DEFAULT")
    if result != {"RUNNING_MODAL"}:
        fail(f"invoke 결과 {result}")
    palette = module.load_palette(module.palette_image_path(bpy.context))
    state = {}

    def overlay():
        # 모달 연산자의 오버레이는 draw 핸들러 인자로만 보이므로 동일 계산으로 재현한다.
        with bpy.context.temp_override(window=window, area=area, region=region):
            return module.PaletteOverlay.fit(bpy.context, palette, region)

    def step_hover():
        ov = overlay()
        # 우측 하단 배치: 오른쪽·아래 여백이 PALETTE_MARGIN
        if abs(ov.bottom - module.PALETTE_MARGIN) > 0.5:
            fail(f"팔레트가 하단에 붙지 않음 bottom={ov.bottom}")
        if ov.left + ov.draw_width < region.width * 0.6:
            fail("팔레트가 우측에 있지 않음")
        state["ov"] = ov
        cell = (5, 3)
        x0, y0, x1, y1 = ov.cell_rect(cell)
        state["cell"] = cell
        window.event_simulate("MOUSEMOVE", "NOTHING", x=int(region.x + (x0 + x1) / 2), y=int(region.y + (y0 + y1) / 2))
        return 0.5

    def step_check_hover():
        expected = tuple(round(c, 5) for c in module.palette_cell_uv(palette, state["cell"]))
        uvs = face_uvs(obj)
        if any(uv != expected for uv in uvs):
            fail(f"호버 미리보기 UV 불일치 {uvs[:2]} != {expected}")
        with bpy.context.temp_override(window=window, area=area):
            bpy.ops.screen.screenshot_area(filepath=SHOT)
        window.event_simulate("ESC", "PRESS")
        window.event_simulate("ESC", "RELEASE")
        return 0.5

    def step_check_cancel():
        if face_uvs(obj) != original:
            fail("Esc 후 UV가 복원되지 않음")
        # 오버레이 실제 색 확인: 스크린샷에서 칸 중앙 픽셀 비교 (호버 칸 제외)
        image = bpy.data.images.load(SHOT)
        width, height = image.size
        pixels = list(image.pixels)
        ov = state["ov"]
        errors = []
        for cell in ((0, 0), (20, 10), (40, 5), (60, 20)):
            x0, y0, x1, y1 = ov.cell_rect(cell)
            # screenshot_area는 영역 전체(area)를 찍으므로 area 기준 좌표로 바꾼다.
            px = int((x0 + x1) / 2 + region.x - area.x)
            py = int((y0 + y1) / 2 + region.y - area.y)
            index = (py * width + px) * 4
            got = [round(pixels[index + i] * 255) for i in range(3)]
            want = [int(v) for v in ov.cell_color(cell)[:3]]
            errors.append(max(abs(g - w) for g, w in zip(got, want)))
            print("cell", cell, "screen", got, "palette", want)
        bpy.data.images.remove(image)
        # 감마가 틀리면 수십 단위로 벌어진다. 화면 디더링 정도의 오차는 허용한다.
        if max(errors) > 12:
            fail(f"오버레이 색이 팔레트와 다름 (최대 오차 {max(errors)})")
        # 팔레트는 마우스 위치를 중심으로 뜨므로 첫 호출과 같은 자리로 되돌린다.
        window.event_simulate("MOUSEMOVE", "NOTHING", x=center[0], y=center[1])
        # 두 번째는 Alt+C 단축키로 연다.
        window.event_simulate("LEFT_ALT", "PRESS", x=center[0], y=center[1])
        window.event_simulate("C", "PRESS", x=center[0], y=center[1], alt=True)
        window.event_simulate("C", "RELEASE", x=center[0], y=center[1], alt=True)
        window.event_simulate("LEFT_ALT", "RELEASE", x=center[0], y=center[1])
        return 0.3

    def step_click():
        ov = overlay()
        x0, y0, x1, y1 = ov.cell_rect((10, 7))
        x, y = int(region.x + (x0 + x1) / 2), int(region.y + (y0 + y1) / 2)
        window.event_simulate("MOUSEMOVE", "NOTHING", x=x, y=y)
        window.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        window.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y)
        return 0.5

    def step_check_click():
        expected = tuple(round(c, 5) for c in module.palette_cell_uv(palette, (10, 7)))
        if any(uv != expected for uv in face_uvs(obj)):
            fail("클릭 확정 UV 불일치")
        bpy.ops.ed.undo()
        print("CatTools palette GUI smoke: OK")
        sys.stdout.flush()
        os._exit(0)

    steps = [step_hover, step_check_hover, step_check_cancel, step_click, step_check_click]

    def run():
        try:
            return steps.pop(0)()
        except Exception as error:
            import traceback
            traceback.print_exc()
            fail(repr(error))

    bpy.app.timers.register(run, first_interval=0.5)


def start():
    try:
        setup()
        main()
    except Exception as error:
        import traceback
        traceback.print_exc()
        fail(repr(error))


bpy.app.timers.register(lambda: start(), first_interval=1.5)
