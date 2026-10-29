"""Blender에서 CatTools Merge Edges(마주보는 두 선을 정중앙의 한 선으로 합치기)를 검사합니다."""

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

    spec = importlib.util.spec_from_file_location("cat_tools_merge_edges_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def make_mesh(name, verts, faces=(), edges=()):
    """주어진 정점·면·선으로 메쉬를 만들고 Edit 모드(선 선택 모드)로 들어간다."""
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([Vector(co) for co in verts], list(edges), list(faces))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    return obj


def select_edges(obj, vert_pairs):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    for a, b in vert_pairs:
        edge = bm.edges.get((bm.verts[a], bm.verts[b]))
        assert edge is not None, (a, b)
        edge.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)


def make_cylinders(name, cap_fill):
    """z=-1.2~-0.2와 z=0.2~1.2에 놓인 닫힌 12각 원기둥 두 개를 한 메쉬로 만들고 Edit 모드(면 선택 모드)로 들어간다."""
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    for z in (-0.7, 0.7):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=(cap_fill == "TRIFAN"), segments=12,
            radius1=1.0, radius2=1.0, depth=1.0, matrix=Matrix.Translation((0.0, 0.0, z)),
        )
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    return obj


def select_faces(obj, predicate, extra_edges=()):
    """predicate가 참인 면만 선택한다. extra_edges(정점 인덱스 쌍)는 면과 별개로 추가 선택한다."""
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    for face in bm.faces:
        if predicate(face):
            face.select_set(True)
    for a, b in extra_edges:
        bm.edges.get((bm.verts[a], bm.verts[b])).select_set(True)
    bmesh.update_edit_mesh(obj.data)


def coords(obj):
    return sorted(tuple(round(c, 5) for c in vert.co) for vert in bmesh.from_edit_mesh(obj.data).verts)


def make_pillars(name):
    """
    x=±1.5에 놓인 두 상자를 만든다. Y 방향 선을 한 번씩 잘라 마주보는 옆면이 면 두 개(테두리 정점 6개)로 나뉜다.
    """
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    for x in (-1.5, 1.5):
        result = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((x, 0.0, 0.0)))
        cube_edges = {edge for vert in result["verts"] for edge in vert.link_edges}
        along_y = [edge for edge in cube_edges if abs((edge.verts[0].co - edge.verts[1].co).y) > 0.5]
        bmesh.ops.subdivide_edges(bm, edges=along_y, cuts=1, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    return obj


def normals_consistent(bm) -> bool:
    """두 면이 공유하는 모든 선을 두 면이 서로 반대 방향으로 지나면 노멀이 일관된다."""
    for edge in bm.edges:
        if len(edge.link_loops) == 2:
            first, second = edge.link_loops
            if first.vert is second.vert:
                return False
    return True


def signed_volume(bm) -> float:
    return sum(
        loop_tri[0].vert.co.dot(loop_tri[1].vert.co.cross(loop_tri[2].vert.co)) / 6.0
        for loop_tri in bm.calc_loop_triangles()
    )


def check_crossed_caps() -> None:
    """정점 두 개를 공유하며 X자로 엇갈린 두 뚜껑 면을 Merge한다(두 테두리가 공유 정점에서 네 갈래로 만남)."""
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bm = bmesh.new()
    caps = []
    for tilt, reach in ((20.0, -1.0), (-20.0, 1.0)):
        # 뚜껑 평면은 Y축과 X축을 Y축 둘레로 tilt만큼 돌린 방향이 이루며, 두 뚜껑은 ±Y 정점을 공유한다.
        side = Matrix.Rotation(math.radians(tilt), 3, "Y") @ Vector((0.0, 0.0, 1.0))
        normal = side.cross(Vector((0.0, 1.0, 0.0))).normalized()
        ring = [side * (0.5 * math.cos(math.radians(45 * i))) + Vector((0.0, 0.5 * math.sin(math.radians(45 * i)), 0.0))
                for i in range(8)]
        near = [bm.verts.new(co) for co in ring]
        far = [bm.verts.new(co + normal * reach) for co in ring]
        tube = [bm.faces.new((near[i], near[(i + 1) % 8], far[(i + 1) % 8], far[i])) for i in range(8)]
        cap = bm.faces.new(near)
        tube += [cap, bm.faces.new(far)]
        bmesh.ops.recalc_face_normals(bm, faces=tube)
        caps.append(cap)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    assert len(bm.verts) == 30, len(bm.verts)
    mesh = bpy.data.meshes.new("CrossedCaps")
    for face in bm.faces:
        face.select = face in caps
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("CrossedCaps", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    assert sum(face.select for face in bmesh.from_edit_mesh(obj.data).faces) == 2
    # 정점을 공유한 두 테두리는 Bridge로 잇지 않는다(다리 면이 찌그러짐).
    assert bpy.ops.mesh.cat_bridge() == {"CANCELLED"}
    assert len(bmesh.from_edit_mesh(obj.data).verts) == 30
    assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.verts) == 30 - 6, len(bm.verts)
    assert len(bm.faces) == 18, len(bm.faces)
    assert all(len(edge.link_faces) == 2 for edge in bm.edges), "꺾인 관에 열린 테두리가 남았습니다."
    assert normals_consistent(bm), "합친 관의 노멀이 뒤집혔습니다."
    assert signed_volume(bm) > 0.0
    # 엇갈린 뚜껑 정점은 위아래 짝끼리 x만 다르므로, 합친 정점은 x=0 평면 위에 놓인다.
    assert all(abs(vert.co.x) < 1e-5 for vert in bm.verts if vert.select), "합친 링이 x=0 평면에 있어야 합니다."


def check_bridge(module) -> None:
    """Bridge: 마주보는 면 묶음을 지우고 두 테두리 사이를 관처럼 잇는다. 선 줄 선택도 잇는다."""
    item = next(item for _keymap, item in module.addon_keymaps if item.idname == "mesh.cat_bridge")
    assert (item.type, item.ctrl, item.alt, item.shift) == ("E", True, False, True)

    # 1) 두 상자의 마주보는 옆면(면 2개씩) → 면 4개를 지우고 테두리 정점 6개끼리 사각형 6개로 잇는다.
    obj = make_pillars("Pillars")
    bm = bmesh.from_edit_mesh(obj.data)
    face_count = len(bm.faces)
    select_faces(obj, lambda face: abs(abs(face.calc_center_median().x) - 1.0) < 1e-4)
    assert sum(1 for face in bm.faces if face.select) == 4
    assert bpy.ops.mesh.cat_bridge() == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.faces) == face_count - 4 + 6, len(bm.faces)
    bridged = [face for face in bm.faces if face.select]
    assert len(bridged) == 6 and all(len(face.verts) == 4 for face in bridged)
    # 다리 면은 x=-1~1을 가로지르며 비틀리지 않는다(각 면이 x축 방향으로 길이 2인 선 두 개를 가진다).
    for face in bridged:
        spans = sorted(abs((edge.verts[0].co - edge.verts[1].co).x) for edge in face.edges)
        assert abs(spans[-1] - 2.0) < 1e-5 and abs(spans[-2] - 2.0) < 1e-5, spans
    assert all(len(edge.link_faces) == 2 for edge in bm.edges), "이은 메쉬에 열린 테두리가 남았습니다."
    assert normals_consistent(bm), "다리 면의 노멀 방향이 기존 면과 어긋납니다."
    assert signed_volume(bm) > 0.0, "노멀이 안쪽을 향합니다."

    # 2) 선 선택: 마주보는 두 선 줄(선 4개씩) 사이를 사각형 4개로 잇고, 면은 지우지 않는다.
    verts, faces = [], []
    for x0 in (0.0, 2.0):
        base = len(verts)
        verts += [(x0 + dx, y, 0) for y in range(5) for dx in (0, 1)]
        faces += [(base + 2 * y, base + 2 * y + 1, base + 2 * y + 3, base + 2 * y + 2) for y in range(4)]
    obj = make_mesh("BridgeRows", verts, faces=faces)
    select_edges(obj, [(2 * y + 1, 2 * y + 3) for y in range(4)] + [(10 + 2 * y, 10 + 2 * y + 2) for y in range(4)])
    assert bpy.ops.mesh.cat_bridge() == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.faces) == 8 + 4 and len(bm.verts) == 20, (len(bm.faces), len(bm.verts))
    assert normals_consistent(bm)
    assert all(face.normal.z > 0.99 for face in bm.faces), "다리 면이 기존 면과 같은 쪽을 보아야 합니다."

    # 3) 선 수가 다른 두 줄은 잇지 않는다.
    select_edges(obj, [(0, 2), (12, 14), (14, 16)])
    assert bpy.ops.mesh.cat_bridge() == {"CANCELLED"}

    # 4) Subdivisions: 마주보는 옆면 다리를 4칸으로 나눈다. Smoothness 0이면 고르게 나눈 직선이다.
    obj = make_pillars("Cuts")
    bm = bmesh.from_edit_mesh(obj.data)
    face_count, vert_count = len(bm.faces), len(bm.verts)
    select_faces(obj, lambda face: abs(abs(face.calc_center_median().x) - 1.0) < 1e-4)
    assert bpy.ops.mesh.cat_bridge(cuts=3, smoothness=0.0) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.faces) == face_count - 4 + 6 * 4, len(bm.faces)
    assert len(bm.verts) == vert_count + 6 * 3, len(bm.verts)
    inner_x = sorted({round(vert.co.x, 5) for vert in bm.verts if abs(vert.co.x) < 0.99})
    assert inner_x == [-0.5, 0.0, 0.5], inner_x
    assert all(len(edge.link_faces) == 2 for edge in bm.edges) and normals_consistent(bm)

    # 5) 아치: 두 기둥의 윗면(노멀 +Z)을 이으면 다리가 노멀을 따라 위로 솟았다 내려오는 아치가 된다.
    obj = make_pillars("Arch")
    select_faces(obj, lambda face: face.normal.z > 0.99)
    assert bpy.ops.mesh.cat_bridge(cuts=9) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert all(len(edge.link_faces) == 2 for edge in bm.edges), "아치에 열린 테두리가 남았습니다."
    assert normals_consistent(bm) and signed_volume(bm) > 0.0
    top = max(vert.co.z for vert in bm.verts)
    assert 1.0 < top < 2.5, top
    # 아치 꼭대기는 가운데(x=0)에 있고 좌우 대칭이다.
    peak = [vert for vert in bm.verts if abs(vert.co.z - top) < 1e-5]
    assert all(abs(vert.co.x) < 1e-5 for vert in peak), [tuple(vert.co) for vert in peak]

    # 6) 선 선택 분할: 이어진 면의 흐름(바깥 방향)을 따르므로 같은 평면 위 두 줄은 평면 안에서 나뉜다.
    obj = make_mesh("BridgeRowCuts", verts, faces=faces)
    select_edges(obj, [(2 * y + 1, 2 * y + 3) for y in range(4)] + [(10 + 2 * y, 10 + 2 * y + 2) for y in range(4)])
    assert bpy.ops.mesh.cat_bridge(cuts=1) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.faces) == 8 + 4 * 2 and len(bm.verts) == 20 + 5, (len(bm.faces), len(bm.verts))
    assert all(abs(vert.co.z) < 1e-6 for vert in bm.verts)
    assert all(abs(vert.co.x - 1.5) < 1e-5 for vert in bm.verts if 1.0 < vert.co.x < 2.0)


def main() -> None:
    module, registered_here = load_addon()
    try:
        keymap_ids = [item.idname for _keymap, item in module.addon_keymaps]
        assert "mesh.cat_merge_edges" in keymap_ids, keymap_ids
        item = next(item for _keymap, item in module.addon_keymaps if item.idname == "mesh.cat_merge_edges")
        assert (item.type, item.ctrl, item.alt, item.shift) == ("E", True, True, False)

        # 1) 간격을 두고 마주보는 두 사각형의 안쪽 선 → x=1.1의 한 선으로 합쳐 면 두 개가 공유
        #    오른쪽 사각형은 정점 순서를 뒤집어 짝 방향 판정도 함께 검사한다.
        obj = make_mesh(
            "Gap",
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2.2, 1, 0), (1.2, 1, 0), (1.2, 0, 0), (2.2, 0, 0)],
            faces=[(0, 1, 2, 3), (7, 4, 5, 6)],
        )
        select_edges(obj, [(1, 2), (5, 6)])
        assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
        bm = bmesh.from_edit_mesh(obj.data)
        assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (6, 7, 2), (len(bm.verts), len(bm.edges), len(bm.faces))
        assert coords(obj) == sorted([(0, 0, 0), (1.1, 0, 0), (1.1, 1, 0), (0, 1, 0), (2.2, 1, 0), (2.2, 0, 0)]), coords(obj)
        shared = [edge for edge in bm.edges if len(edge.link_faces) == 2]
        assert len(shared) == 1 and shared[0].select, "합친 선이 두 면에 공유되고 선택되어야 합니다."

        # 2) 선 두 개로 된 줄끼리 마주보면 정점 3쌍을 합친다.
        obj = make_mesh(
            "Strip",
            [(0, 0, 0), (0, 1, 0), (0, 2, 0), (-1, 0, 0), (-1, 1, 0), (-1, 2, 0),
             (0.4, 0, 0), (0.4, 1, 0), (0.4, 2, 0), (1, 0, 0), (1, 1, 0), (1, 2, 0)],
            faces=[(3, 0, 1, 4), (4, 1, 2, 5), (6, 9, 10, 7), (7, 10, 11, 8)],
        )
        select_edges(obj, [(0, 1), (1, 2), (6, 7), (7, 8)])
        assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
        bm = bmesh.from_edit_mesh(obj.data)
        assert len(bm.verts) == 9, len(bm.verts)
        # 각 줄 안쪽의 기존 공유 선 2개 + 새로 합친 선 2개
        assert sum(1 for edge in bm.edges if len(edge.link_faces) == 2) == 4

        # 3) 꼭짓점을 공유하는 V자 두 선 → 벌어진 끝을 합쳐 틈을 닫는다.
        obj = make_mesh(
            "Vee",
            [(0, 0, 0), (-0.1, 1, 0), (0.1, 1, 0), (-1, 1, 0), (1, 1, 0)],
            faces=[(0, 1, 3), (0, 4, 2)],
        )
        select_edges(obj, [(0, 1), (0, 2)])
        assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
        assert coords(obj) == sorted([(0, 0, 0), (0, 1, 0), (-1, 1, 0), (1, 1, 0)]), coords(obj)

        # 4) 회전·방향이 어긋난 두 닫힌 루프도 가장 가까운 정렬로 짝지어 합친다.
        count = 8
        lower = [(math.cos(2 * math.pi * i / count), math.sin(2 * math.pi * i / count), 0) for i in range(count)]
        upper = [(math.cos(-2 * math.pi * (i + 3) / count), math.sin(-2 * math.pi * (i + 3) / count), 0.2)
                 for i in range(count)]
        ring = [(i, (i + 1) % count) for i in range(count)]
        obj = make_mesh("Loops", lower + upper, edges=ring + [(a + count, b + count) for a, b in ring])
        select_edges(obj, ring + [(a + count, b + count) for a, b in ring])
        assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
        bm = bmesh.from_edit_mesh(obj.data)
        assert (len(bm.verts), len(bm.edges)) == (count, count), (len(bm.verts), len(bm.edges))
        assert all(abs(vert.co.z - 0.1) < 1e-5 and abs(vert.co.xy.length - 1) < 1e-5 for vert in bm.verts)

        # 5) 4x1 격자 두 장의 마주보는 경계 줄(선 4개씩)과, 떨어진 곳의 또 다른 선 한 쌍을 한 번에 합친다.
        verts, faces = [], []
        for x0 in (0.0, 1.2):
            base = len(verts)
            verts += [(x0 + dx, y, 0) for y in range(5) for dx in (0, 1)]
            faces += [(base + 2 * y, base + 2 * y + 1, base + 2 * y + 3, base + 2 * y + 2) for y in range(4)]
        base = len(verts)
        verts += [(0, 10, 0), (1, 10, 0), (1, 11, 0), (0, 11, 0), (1.3, 10, 0), (2.3, 10, 0), (2.3, 11, 0), (1.3, 11, 0)]
        faces += [(base, base + 1, base + 2, base + 3), (base + 4, base + 5, base + 6, base + 7)]
        obj = make_mesh("Rows", verts, faces=faces)
        left_row = [(2 * y + 1, 2 * y + 3) for y in range(4)]
        right_row = [(10 + 2 * y, 10 + 2 * y + 2) for y in range(4)]
        select_edges(obj, left_row + right_row + [(base + 1, base + 2), (base + 4, base + 7)])
        assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
        bm = bmesh.from_edit_mesh(obj.data)
        assert len(bm.verts) == 28 - 5 - 2, len(bm.verts)
        merged_x = sorted({round(vert.co.x, 5) for vert in bm.verts if vert.select})
        assert merged_x == [1.1, 1.15], merged_x
        assert sum(1 for edge in bm.edges if len(edge.link_faces) == 2) == 3 * 2 + 4 + 1

        # 6) 짝을 정할 수 없는 선택(떨어진 선 세 개, 선 수가 다른 두 줄)은 아무것도 바꾸지 않는다.
        obj = make_mesh(
            "Invalid",
            [(0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0), (2, 0, 0), (2, 1, 0), (2, 2, 0)],
            edges=[(0, 1), (2, 3), (4, 5), (5, 6)],
        )
        before = coords(obj)
        select_edges(obj, [(0, 1), (2, 3), (4, 5)])
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        select_edges(obj, [(0, 1), (4, 5), (5, 6)])
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        select_edges(obj, [])
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        assert coords(obj) == before

        # 7) 면 선택: 닫힌 두 원기둥의 마주보는 뚜껑 면 → 면을 지우고 테두리를 정중앙에서 이어 한 관으로 만든다.
        for cap_fill in ("NGON", "TRIFAN"):
            obj = make_cylinders("Tubes", cap_fill)
            select_faces(obj, lambda face: abs(face.calc_center_median().z) < 0.2 + 1e-4)
            assert bpy.ops.mesh.cat_merge_edges() == {"FINISHED"}
            bm = bmesh.from_edit_mesh(obj.data)
            sides = [face for face in bm.faces if len(face.verts) == 4]
            assert len(sides) == 24, (cap_fill, len(sides))
            # 위아래 바깥 뚜껑만 남고, 정점은 링 세 개(바깥 둘 + 가운데 합친 링) + 부채꼴 중심.
            centers = 2 if cap_fill == "TRIFAN" else 0
            assert len(bm.verts) == 12 * 3 + centers, (cap_fill, len(bm.verts))
            assert all(len(edge.link_faces) == 2 for edge in bm.edges), "이어 붙인 관에 열린 테두리가 남았습니다."
            middle = [vert for vert in bm.verts if abs(vert.co.z) < 1e-5]
            assert len(middle) == 12 and all(vert.select for vert in middle), "가운데 링이 z=0에서 선택되어야 합니다."
            assert all(abs(vert.co.xy.length - 1.0) < 1e-5 for vert in middle)

        # 8) 면 선택이지만 짝지을 수 없는 경우(테두리 정점 수가 다름, 붙어 있는 두 면, 면 + 떨어진 선)는 바꾸지 않는다.
        obj = make_mesh(
            "BadFaces",
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (3, 0, 0), (2.5, 1, 0), (2, 1, 0), (3, 1, 0),
             (5, 0, 0), (5, 1, 0)],
            faces=[(0, 1, 2, 3), (4, 5, 6), (1, 4, 7, 2)],
            edges=[(9, 10)],
        )
        before = coords(obj)
        select_faces(obj, lambda face: len(face.verts) == 3 or face.calc_center_median().x < 0.6)
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        select_faces(obj, lambda face: len(face.verts) == 4)
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        select_faces(obj, lambda face: face.calc_center_median().x < 0.6, extra_edges=[(9, 10)])
        assert bpy.ops.mesh.cat_merge_edges() == {"CANCELLED"}
        assert coords(obj) == before
        assert len(bmesh.from_edit_mesh(obj.data).faces) == 3
        assert bpy.ops.mesh.cat_bridge() == {"CANCELLED"}
        assert coords(obj) == before

        # 9) X자로 엇갈려 위아래 정점 두 개를 공유한 두 8각 뚜껑(용 몸통 관절처럼 꺾인 두 관) → 공유 정점은 그대로,
        #    나머지 6쌍만 정중앙에서 합쳐 노멀이 일관된 꺾인 관이 된다.
        check_crossed_caps()

        check_bridge(module)
        print("CatTools merge edges smoke: OK")
    finally:
        if registered_here:
            module.unregister()


main()
