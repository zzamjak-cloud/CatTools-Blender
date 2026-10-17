"""Blender에서 CatTools Palette Color(선택 면 UV를 팔레트 색 칸 중앙으로 이동)를 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import os
import tempfile
from pathlib import Path

import bmesh
import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"

# 4열 x 2행, 칸 크기 4x8 픽셀인 합성 팔레트 (위 행부터)
COLUMNS, ROWS, CELL_W, CELL_H = 4, 2, 4, 8
CELL_COLORS = [
    [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)],
    [(0, 255, 255), (255, 0, 255), (255, 255, 255), (0, 0, 0)],
]


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_palette_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def write_palette(path: str) -> None:
    width, height = COLUMNS * CELL_W, ROWS * CELL_H
    image = bpy.data.images.new("palette_smoke", width, height, alpha=True)
    pixels = []
    # Blender 픽셀은 아래 행부터 채운다.
    for y in range(height - 1, -1, -1):
        for x in range(width):
            red, green, blue = CELL_COLORS[y // CELL_H][x // CELL_W]
            pixels.extend((red / 255, green / 255, blue / 255, 1.0))
    image.pixels.foreach_set(pixels)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def make_cube(with_uv: bool = True):
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("PaletteCube")
    bm = bmesh.new()
    if with_uv:
        bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=2.0, calc_uvs=with_uv)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("PaletteCube", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    # 선택 해제를 먼저 끝내야 공유 정점 때문에 고른 면이 다시 풀리지 않는다.
    for face in bm.faces:
        face.select_set(False)
    for face in list(bm.faces)[:2]:
        face.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    return obj


def make_cube_object(name: str, uv):
    """모든 UV가 uv 한 점인 Object 모드 큐브."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    layer = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=1.0)
    for face in bm.faces:
        for loop in face.loops:
            loop[layer].uv = uv
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def face_uvs(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    layer = bm.loops.layers.uv.active
    return [[tuple(round(c, 6) for c in loop[layer].uv) for loop in face.loops] for face in bm.faces]


def main() -> None:
    module, registered_here = load_addon()
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "palette.png")
            write_palette(path)
            palette = module.load_palette(path)
            assert (palette["cell_width"], palette["cell_height"]) == (CELL_W, CELL_H), palette
            assert (palette["columns"], palette["rows"]) == (COLUMNS, ROWS), palette
            assert tuple(palette["cell_colors"][1, 2][:3]) == CELL_COLORS[1][2]
            assert module.palette_cell_uv(palette, (2, 1)) == (0.625, 0.25)

            # 오버레이 좌표 → 칸 변환: 왼쪽 아래 (0,0), 배율 10
            class Region:
                def as_pointer(self):
                    return 1
            overlay = module.PaletteOverlay(palette, Region(), 0.0, 0.0, 10.0)
            assert overlay.cell_at(5, 155) == (0, 0)
            assert overlay.cell_at(125, 5) == (3, 1)
            assert overlay.cell_at(-1, 5) is None and overlay.cell_at(5, 161) is None

            # 사용 중인 칸: 경계값 1.0은 감싸지 않고, 범위 밖 UV는 반복처럼 감싼다.
            points = np.array([(0.1, 0.9), (0.12, 0.95), (1.0, 0.0), (1.625, 0.25)], dtype=np.float32)
            assert module.palette_used_cells(palette, points) == [(0, 0), (2, 1), (3, 1)], (
                module.palette_used_cells(palette, points)
            )

            # 팔레트 이미지를 쓰는 머티리얼이 있으면 그 메쉬의 UV만 모은다.
            make_cube()
            bpy.ops.object.mode_set(mode="OBJECT")
            other = make_cube_object("Other", (0.9, 0.9))
            image = bpy.data.images.load(path)
            material = bpy.data.materials.new("PaletteMat")
            material.use_nodes = True
            node = material.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            other.data.materials.append(material)
            # 새로 링크한 오브젝트는 뷰 레이어 동기화 뒤에 view_layer.objects에 나타난다.
            bpy.context.view_layer.update()
            points = module.palette_uv_points(bpy.context, path)
            assert len(points) == 24 and np.allclose(points, (0.9, 0.9)), points[:3]
            # 노드 그룹 안의 Image Texture도 찾는다.
            group = bpy.data.node_groups.new("PaletteGroup", "ShaderNodeTree")
            group.nodes.new("ShaderNodeTexImage").image = image
            grouped = bpy.data.materials.new("GroupedMat")
            grouped.use_nodes = True
            grouped.node_tree.nodes.new("ShaderNodeGroup").node_tree = group
            assert module.material_uses_image(grouped, path)
            other.data.materials.clear()
            assert len(module.palette_uv_points(bpy.context, path)) == 48
            bpy.data.objects.remove(other)

        obj = make_cube()
        before = face_uvs(obj)
        snapshot = module.capture_face_uvs(bpy.context)
        assert module.apply_palette_uv(bpy.context, (0.1, 0.9)) == 2
        module.restore_face_uvs(bpy.context, snapshot)
        assert face_uvs(obj) == before, "미리보기 취소 후 UV가 복원되지 않았습니다."

        result = bpy.ops.mesh.cat_palette_color(u=0.625, v=0.25)
        assert result == {"FINISHED"}, result
        after = face_uvs(obj)
        for index, uvs in enumerate(after):
            if index < 2:
                assert all(uv == (0.625, 0.25) for uv in uvs), uvs
            else:
                assert uvs == before[index], "선택하지 않은 면의 UV가 바뀌었습니다."

        # 선택 면이 없으면 취소
        bm = bmesh.from_edit_mesh(obj.data)
        for face in bm.faces:
            face.select_set(False)
        bmesh.update_edit_mesh(obj.data)
        assert bpy.ops.mesh.cat_palette_color(u=0.5, v=0.5) == {"CANCELLED"}

        # UV가 없던 메쉬는 미리보기로 만든 UV 레이어를 취소 시 지우고, 확정 시 새로 만든다.
        obj = make_cube(with_uv=False)
        snapshot = module.capture_face_uvs(bpy.context)
        module.apply_palette_uv(bpy.context, (0.3, 0.3))
        module.restore_face_uvs(bpy.context, snapshot)
        assert bmesh.from_edit_mesh(obj.data).loops.layers.uv.active is None
        assert bpy.ops.mesh.cat_palette_color(u=0.3, v=0.7) == {"FINISHED"}
        assert face_uvs(obj)[0] == [(0.3, 0.7)] * 4
        print("CatTools palette smoke: OK")
    finally:
        if registered_here:
            module.unregister()


main()
