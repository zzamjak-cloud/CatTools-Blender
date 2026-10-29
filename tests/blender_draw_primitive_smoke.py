"""Blender에서 CatTools Modeling의 Cylinder·Cube 생성(Quick Function 재실행 경로)을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_draw_primitive_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def flat(matrix: Matrix):
    return [value for row in matrix for value in row]


def clear_scene() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def signed_volume(obj) -> float:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    volume = sum(
        tri[0].vert.co.dot(tri[1].vert.co.cross(tri[2].vert.co)) / 6.0 for tri in bm.calc_loop_triangles()
    )
    manifold = all(len(edge.link_faces) == 2 for edge in bm.edges)
    bm.free()
    return volume if manifold else float("nan")


def world_bounds(obj):
    points = [obj.matrix_world @ vert.co for vert in obj.data.vertices]
    return (
        Vector(tuple(min(p[i] for p in points) for i in range(3))),
        Vector(tuple(max(p[i] for p in points) for i in range(3))),
    )


def main() -> None:
    module, registered_here = load_addon()
    try:
        assert module.VIEW3D_OT_CatDrawPrimitive.poll(bpy.context)
        clear_scene()

        # 1) 실린더: 둘레 U, 높이 V 분할. 바닥 중심이 원점이고 +Z로 선다.
        base = Matrix.Translation((1.0, 2.0, 3.0))
        result = bpy.ops.view3d.cat_draw_primitive(
            shape="CYLINDER", base_matrix=flat(base), radius=0.5, height=2.0, resolution_u=8, resolution_v=3,
        )
        assert result == {"FINISHED"}, result
        obj = bpy.context.active_object
        assert obj.name.startswith("Cylinder") and obj.select_get()
        assert len(obj.data.vertices) == 8 * 4, len(obj.data.vertices)
        assert len(obj.data.polygons) == 8 * 3 + 2, len(obj.data.polygons)
        low, high = world_bounds(obj)
        assert abs(low.z - 3.0) < 1e-5 and abs(high.z - 5.0) < 1e-5, (low, high)
        assert abs(high.x - 1.5) < 1e-5 and abs(low.x - 0.5) < 1e-5, (low, high)
        assert (obj.matrix_world.translation - Vector((1.0, 2.0, 3.0))).length < 1e-6
        assert signed_volume(obj) > 0.0, "실린더 노멀이 바깥을 보아야 합니다."

        # 2) 큐브: X·Y·Z 분할. 정점·면 수가 분할된 상자와 같고 크기가 맞는다.
        rx, ry, rz = 2, 3, 4
        result = bpy.ops.view3d.cat_draw_primitive(
            shape="CUBE", base_matrix=flat(Matrix.Identity(4)), size_x=2.0, size_y=3.0, height=1.5,
            resolution_x=rx, resolution_y=ry, resolution_z=rz,
        )
        assert result == {"FINISHED"}, result
        obj = bpy.context.active_object
        assert obj.name.startswith("Cube")
        expected_verts = (rx + 1) * (ry + 1) * (rz + 1) - (rx - 1) * (ry - 1) * (rz - 1)
        assert len(obj.data.vertices) == expected_verts, (len(obj.data.vertices), expected_verts)
        assert len(obj.data.polygons) == 2 * (rx * ry + ry * rz + rx * rz), len(obj.data.polygons)
        low, high = world_bounds(obj)
        assert (low - Vector((-1.0, -1.5, 0.0))).length < 1e-5 and (high - Vector((1.0, 1.5, 1.5))).length < 1e-5
        assert signed_volume(obj) > 0.0, "큐브가 닫힌 상자이고 노멀이 바깥을 보아야 합니다."

        # 3) 기울어진 면 위(노멀 = 월드 X): 오브젝트 Z축이 노멀을 따르고, 음수 높이도 노멀이 바깥을 본다.
        frame = module.frame_matrix(Vector((5.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)))
        result = bpy.ops.view3d.cat_draw_primitive(
            shape="CUBE", base_matrix=flat(frame), size_x=1.0, size_y=1.0, height=-0.5,
        )
        assert result == {"FINISHED"}
        obj = bpy.context.active_object
        assert (obj.matrix_world.col[2].xyz - Vector((1.0, 0.0, 0.0))).length < 1e-6
        low, high = world_bounds(obj)
        assert abs(low.x - 4.5) < 1e-5 and abs(high.x - 5.0) < 1e-5, (low, high)
        assert signed_volume(obj) > 0.0, "음수 높이에서도 노멀이 바깥을 보아야 합니다."

        # 4) 면 좌표계: X축은 면의 첫 선을 평면에 투영한 방향, 노멀과 수직인 오른손 좌표계.
        normal = Vector((0.0, 0.0, 1.0))
        axis = module.plane_axis(normal, Vector((1.0, 1.0, 0.7)))
        assert abs(axis.dot(normal)) < 1e-6 and abs(axis.length - 1.0) < 1e-6
        assert (axis - Vector((1.0, 1.0, 0.0)).normalized()).length < 1e-6
        assert abs(module.frame_matrix(Vector(), normal, axis).to_3x3().determinant() - 1.0) < 1e-6

        # 5) Edit 모드에서 실행하면 Object 모드로 나와 새 오브젝트를 만든다.
        bpy.ops.object.mode_set(mode="EDIT")
        assert module.VIEW3D_OT_CatDrawPrimitive.poll(bpy.context)
        assert bpy.ops.view3d.cat_draw_primitive(shape="CYLINDER", radius=1.0, height=1.0) == {"FINISHED"}
        assert bpy.context.mode == "OBJECT" and bpy.context.active_object.name.startswith("Cylinder")
        assert len(bpy.data.objects) == 4
        print("CatTools draw primitive smoke: OK")
    finally:
        if registered_here:
            module.unregister()


main()
