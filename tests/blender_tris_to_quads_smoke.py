"""Blender에서 CatTools Tris to Quads(삼각형 두 개 사이 대각선을 지워 사각형 만들기)를 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
import random
from pathlib import Path

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_tris_to_quads_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def make_grid(name, size=6, shear=0.0, wave=0.0, triangulate=lambda face: True, ngon=False):
    """
    size x size 사각 격자를 만들고, triangulate가 참인 사각형을 무작위 방향 대각선으로 나눈다.

    ngon이면 격자 한쪽에 오각형 하나를 붙인다. 모든 면을 선택한 채 Edit 모드로 들어간다.
    """
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    grid = [
        [bm.verts.new((x + shear * y, y, wave * math.sin(x * 0.9) * math.cos(y * 0.7))) for x in range(size + 1)]
        for y in range(size + 1)
    ]
    rng = random.Random(7)
    quads = 0
    for y in range(size):
        for x in range(size):
            a, b, c, d = grid[y][x], grid[y][x + 1], grid[y + 1][x + 1], grid[y + 1][x]
            if triangulate((x, y)):
                if rng.random() < 0.5:
                    bm.faces.new((a, b, c))
                    bm.faces.new((a, c, d))
                else:
                    bm.faces.new((a, b, d))
                    bm.faces.new((b, c, d))
            else:
                bm.faces.new((a, b, c, d))
                quads += 1
    if ngon:
        top = grid[size]
        apex = bm.verts.new((size * 0.5 + shear * size, size + 1.0, 0.0))
        bm.faces.new((top[0], top[size], apex, top[size // 2 + 1], top[size // 2]))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action="SELECT")
    return obj, quads


def face_sizes(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    sizes = {}
    for face in bm.faces:
        sizes[len(face.verts)] = sizes.get(len(face.verts), 0) + 1
    return sizes


def main() -> None:
    module, registered_here = load_addon()
    try:
        item = next(item for _keymap, item in module.addon_keymaps if item.idname == "mesh.cat_tris_to_quads")
        assert (item.type, item.ctrl, item.alt, item.shift) == ("J", True, True, False)

        # 1) 사각형·N각형이 섞이고 대각선 방향이 제각각인 격자 → 모든 삼각형이 원래 격자 사각형으로 돌아간다.
        obj, quads = make_grid("Mixed", triangulate=lambda cell: (cell[0] + cell[1]) % 3 != 0, ngon=True)
        triangles = face_sizes(obj)[3]
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {4: quads + triangles // 2, 5: 1}, face_sizes(obj)
        bm = bmesh.from_edit_mesh(obj.data)
        assert all(face.select for face in bm.faces), "합친 사각형은 선택된 상태로 남아야 합니다."
        # 격자 사각형으로 돌아갔다면 모든 사각형의 네 변이 축 방향(길이 1)이다.
        for face in bm.faces:
            if len(face.verts) == 4:
                assert all(abs(edge.calc_length() - 1.0) < 1e-5 for edge in face.edges)

        # 2) 기울어진(평행사변형) 격자 + 굴곡: 직각이 아니어도 원래 대각선만 지운다.
        obj, _quads = make_grid("Sheared", shear=0.6, wave=0.15)
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {4: 36}, face_sizes(obj)

        # 3) 일부 면만 선택: 선택하지 않은 삼각형은 건드리지 않고, 선택 경계를 넘어 짝짓지 않는다.
        obj, _quads = make_grid("Partial")
        bm = bmesh.from_edit_mesh(obj.data)
        for face in bm.faces:
            face.select = face.calc_center_median().x < 3.0
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {3: 36, 4: 18}, face_sizes(obj)

        # 4) 짝이 없는 삼각형(홀수)은 남기고 나머지만 합친다.
        obj, quads = make_grid("Odd", size=1)
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.faces[1].select = False
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {3: 2}, face_sizes(obj)

        # 5) 크게 접힌 두 삼각형은 Max Angle을 넘으면 합치지 않고, 올리면 합친다.
        obj, _quads = make_grid("Fold", size=1)
        bm = bmesh.from_edit_mesh(obj.data)
        diagonal = next(edge for edge in bm.edges if len(edge.link_faces) == 2)
        tip = next(vert for vert in diagonal.link_faces[0].verts if vert not in diagonal.verts)
        tip.co.z = 1.0  # 대각선을 따라 약 55° 접힌다.
        bm.normal_update()
        bmesh.update_edit_mesh(obj.data)
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {3: 2}, face_sizes(obj)
        assert bpy.ops.mesh.cat_tris_to_quads(max_angle=math.radians(90.0)) == {"FINISHED"}
        assert face_sizes(obj) == {4: 1}, face_sizes(obj)

        # 6) 삼각형이 없거나 아무것도 선택하지 않으면 바꾸지 않는다.
        obj, _quads = make_grid("Quads", size=2, triangulate=lambda cell: False)
        assert bpy.ops.mesh.cat_tris_to_quads() == {"CANCELLED"}
        bpy.ops.mesh.select_all(action="DESELECT")
        assert bpy.ops.mesh.cat_tris_to_quads() == {"CANCELLED"}
        assert face_sizes(obj) == {4: 4}

        # 7) 구의 극점 삼각형 부채꼴은 원래 삼각형이므로 기본 Shape Limit에서는 남기고, 90°로 풀면 합친다.
        if bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        obj = bpy.context.object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.quads_convert_to_tris()
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        assert face_sizes(obj) == {3: 32, 4: 96}, face_sizes(obj)
        assert bpy.ops.mesh.cat_tris_to_quads(shape_limit=math.radians(90.0)) == {"FINISHED"}
        assert face_sizes(obj) == {4: 112}, face_sizes(obj)

        # 8) 큰 메쉬도 빠르게 처리한다 (40 x 40 격자 = 삼각형 3200개).
        import time
        obj, _quads = make_grid("Large", size=40, wave=0.3)
        start = time.perf_counter()
        assert bpy.ops.mesh.cat_tris_to_quads() == {"FINISHED"}
        elapsed = time.perf_counter() - start
        assert face_sizes(obj) == {4: 1600}, face_sizes(obj)
        assert elapsed < 2.0, elapsed
        print(f"CatTools tris to quads smoke: OK ({elapsed * 1000:.0f} ms for 3200 tris)")
    finally:
        if registered_here:
            module.unregister()


main()
