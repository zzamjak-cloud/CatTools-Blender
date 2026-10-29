"""Blender에서 CatTools Modeling의 Reduce Sides(원통·원뿔 둘레 각 줄이기)를 검사합니다."""

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

    spec = importlib.util.spec_from_file_location("cat_tools_reduce_sides_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def clear_scene() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def edit(obj, select_all=True) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT" if select_all else "DESELECT")


def ring_angles(points, center: Vector, axis: Vector):
    """축 둘레 각도(도)를 정렬해 돌려준다. 축 위 정점은 뺀다."""
    u = Vector((1.0, 0.0, 0.0)) if abs(axis.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    u = (u - axis * u.dot(axis)).normalized()
    v = axis.cross(u)
    angles = set()
    for point in points:
        offset = point - center
        offset -= axis * offset.dot(axis)
        if offset.length > 1e-5:
            angles.add(round(math.degrees(math.atan2(offset.dot(v), offset.dot(u))) % 360.0, 3) % 360.0)
    return sorted(angles)


def evenly_spaced(angles, sides) -> bool:
    if len(angles) != sides:
        return False
    gaps = [(angles[(i + 1) % sides] - angles[i]) % 360.0 for i in range(sides)]
    return all(abs(gap - 360.0 / sides) < 1e-2 for gap in gaps)


def manifold(mesh) -> bool:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    result = all(len(edge.link_faces) == 2 for edge in bm.edges)
    bm.free()
    return result


def radii(points, center: Vector, axis: Vector):
    values = []
    for point in points:
        offset = point - center
        offset -= axis * offset.dot(axis)
        if offset.length > 1e-5:
            values.append(round(offset.length, 4))
    return sorted(set(values))


def main() -> None:
    module, registered_here = load_addon()
    try:
        z = Vector((0.0, 0.0, 1.0))

        # 1) N각형 뚜껑 12각 실린더 → 6각: 정점 12개, 면 6+2, 반지름·높이 유지, 닫힌 형태
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=1.0, depth=2.0, end_fill_type="NGON")
        obj = bpy.context.active_object
        edit(obj)
        assert module.MESH_OT_CatReduceSides.poll(bpy.context)
        assert bpy.ops.mesh.cat_reduce_sides(sides=6) == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        points = [v.co.copy() for v in obj.data.vertices]
        assert len(points) == 12 and len(obj.data.polygons) == 8, (len(points), len(obj.data.polygons))
        assert evenly_spaced(ring_angles(points, Vector(), z), 6)
        assert radii(points, Vector(), z) == [1.0], radii(points, Vector(), z)
        assert sorted({round(p.z, 4) for p in points}) == [-1.0, 1.0]
        assert manifold(obj.data)

        # 2) 삼각형 부채꼴 바닥 원뿔 12각 → 5각: 원래 각도와 맞지 않아도 72° 간격으로 고르게 편다
        clear_scene()
        bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=1.0, depth=2.0, end_fill_type="TRIFAN")
        obj = bpy.context.active_object
        edit(obj)
        assert bpy.ops.mesh.cat_reduce_sides(sides=5) == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        points = [v.co.copy() for v in obj.data.vertices]
        assert len(points) == 5 + 2, len(points)
        assert len(obj.data.polygons) == 10, len(obj.data.polygons)
        assert all(len(p.vertices) == 3 for p in obj.data.polygons)
        assert evenly_spaced(ring_angles(points, Vector(), z), 5)
        assert manifold(obj.data)

        # 3) 세로로 3칸 나뉜 부채꼴 뚜껑 실린더 12각 → 8각: 링마다 8각, 사각형 옆면 유지
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.5, depth=3.0, end_fill_type="TRIFAN")
        obj = bpy.context.active_object
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        vertical = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co).normalized().z) > 0.99]
        bmesh.ops.subdivide_edges(bm, edges=vertical, cuts=2, use_grid_fill=True)
        bm.to_mesh(obj.data)
        bm.free()
        edit(obj)
        assert bpy.ops.mesh.cat_reduce_sides(sides=8) == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        points = [v.co.copy() for v in obj.data.vertices]
        assert len(points) == 8 * 4 + 2, len(points)
        assert sum(len(p.vertices) == 4 for p in obj.data.polygons) == 8 * 3
        assert evenly_spaced(ring_angles(points, Vector(), z), 8)
        assert radii(points, Vector(), z) == [0.5]
        assert manifold(obj.data)

        # 4) 한 오브젝트 안 여러 덩어리(L로 고른 것처럼): 기울어진 팔 두 개는 각자 축으로 6각, 고르지 않은 덩어리는 그대로
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.3, depth=2.0)
        obj = bpy.context.active_object
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        arm = Matrix.Translation((2.0, 0.0, 1.0)) @ Matrix.Rotation(math.radians(50.0), 4, "Y")
        bmesh.ops.transform(bm, matrix=arm, verts=bm.verts)
        copy = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
        other = [g for g in copy["geom"] if isinstance(g, bmesh.types.BMVert)]
        mirror = Matrix.Scale(-1.0, 4, (1.0, 0.0, 0.0))
        bmesh.ops.transform(bm, matrix=mirror, verts=other)
        bmesh.ops.reverse_faces(bm, faces=[g for g in copy["geom"] if isinstance(g, bmesh.types.BMFace)])
        untouched = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.3, depth=1.0,
                                          matrix=Matrix.Translation((0.0, 5.0, 0.0)))
        untouched_verts = set(untouched["verts"])
        for vert in bm.verts:
            vert.select_set(vert not in untouched_verts)
        bm.to_mesh(obj.data)
        bm.free()
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        assert bpy.ops.mesh.cat_reduce_sides(sides=6) == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        assert len(obj.data.vertices) == 12 + 12 + 24, len(obj.data.vertices)
        for sign in (1.0, -1.0):
            arm_axis = Vector((sign * math.sin(math.radians(50.0)), 0.0, math.cos(math.radians(50.0))))
            center = Vector((2.0 * sign, 0.0, 1.0))
            points = [v.co.copy() for v in obj.data.vertices if (v.co - center).length < 1.5]
            assert len(points) == 12, len(points)
            assert evenly_spaced(ring_angles(points, center, arm_axis), 6), ring_angles(points, center, arm_axis)
            assert radii(points, center, arm_axis) == [0.3]
        assert manifold(obj.data)

        # 5) Object 모드: 선택한 오브젝트 전체, 뚜껑 없는 관 12각 → 4각. Keep Area면 단면 넓이를 유지한다
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=1.0, depth=1.0, end_fill_type="NOTHING")
        obj = bpy.context.active_object
        assert module.MESH_OT_CatReduceSides.poll(bpy.context)
        assert bpy.ops.mesh.cat_reduce_sides(sides=4, keep_area=True) == {"FINISHED"}
        points = [v.co.copy() for v in obj.data.vertices]
        assert len(points) == 8 and len(obj.data.polygons) == 4
        assert evenly_spaced(ring_angles(points, Vector(), z), 4)
        expected = math.sqrt((12 * math.sin(2 * math.pi / 12)) / (4 * math.sin(2 * math.pi / 4)))
        assert abs(radii(points, Vector(), z)[0] - expected) < 1e-3, radii(points, Vector(), z)

        # 6) Offset: 6각에서 남기는 줄을 한 칸 돌리면 각도가 30° 어긋난다
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12)
        obj = bpy.context.active_object
        assert bpy.ops.mesh.cat_reduce_sides(sides=6) == {"FINISHED"}
        first = ring_angles([v.co.copy() for v in obj.data.vertices], Vector(), z)
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=12)
        obj = bpy.context.active_object
        assert bpy.ops.mesh.cat_reduce_sides(sides=6, offset=1) == {"FINISHED"}
        second = ring_angles([v.co.copy() for v in obj.data.vertices], Vector(), z)
        assert abs(((second[0] - first[0]) % 60.0) - 30.0) < 1e-2, (first, second)

        # 7) 손으로 다듬은 팔처럼 가늘어지고 비틀린(링마다 25°) 기울어진 관도 선 연결로 살을 찾아 6각으로 줄인다
        clear_scene()
        mesh = bpy.data.meshes.new("TwistedArm")
        obj = bpy.data.objects.new("TwistedArm", mesh)
        bpy.context.collection.objects.link(obj)
        bm = bmesh.new()
        rings = [
            [bm.verts.new(((0.4 - 0.04 * r) * math.cos(math.radians(30 * i + 25 * r)),
                           (0.4 - 0.04 * r) * math.sin(math.radians(30 * i + 25 * r)), 0.5 * r)) for i in range(12)]
            for r in range(6)
        ]
        for r in range(5):
            for i in range(12):
                bm.faces.new((rings[r][i], rings[r][(i + 1) % 12], rings[r + 1][(i + 1) % 12], rings[r + 1][i]))
        bmesh.ops.transform(bm, matrix=Matrix.Rotation(math.radians(45.0), 4, "Y"), verts=bm.verts)
        bm.to_mesh(mesh)
        bm.free()
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        assert bpy.ops.mesh.cat_reduce_sides(sides=6) == {"FINISHED"}
        assert len(mesh.vertices) == 6 * 6 and len(mesh.polygons) == 6 * 5
        assert all(len(p.vertices) == 4 for p in mesh.polygons)

        # 8) 원통이 아닌 형태(Suzanne)나 원래보다 많은 각은 손대지 않고 취소한다
        clear_scene()
        bpy.ops.mesh.primitive_monkey_add()
        obj = bpy.context.active_object
        before = len(obj.data.vertices)
        assert bpy.ops.mesh.cat_reduce_sides(sides=6) == {"CANCELLED"}
        assert len(obj.data.vertices) == before
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(vertices=8)
        obj = bpy.context.active_object
        assert bpy.ops.mesh.cat_reduce_sides(sides=8) == {"CANCELLED"}
        assert len(obj.data.vertices) == 16
        print("CatTools reduce sides smoke: OK")
    finally:
        if registered_here:
            module.unregister()


main()
