"""Blender에서 Catoon 셀셰이딩 머티리얼을 실제로 렌더링해 2톤 결과를 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
import tempfile
from collections import Counter
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"

# 텍스처 색감이 그대로 살아나는지 확인하기 위한 기준 색 (Non-Color로 통과시킨다)
TEXTURE_COLOR = (0.80, 0.25, 0.10)
SHADOW_TINT = (0.45, 0.5, 0.62)
TOLERANCE = 0.02


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_catoon_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, True


def remove_all_objects() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def eevee_engine() -> str:
    items = [
        item.identifier
        for item in bpy.context.scene.render.bl_rna.properties["engine"].enum_items
        if "EEVEE" in item.identifier
    ]
    if not items:
        raise AssertionError("EEVEE 렌더 엔진을 찾을 수 없습니다.")
    return items[0]


def build_scene():
    """구체 + 태양광으로 밝은 면과 그림자 면이 모두 생기는 장면을 만든다."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=(0.0, 0.0, 0.0))
    sphere = bpy.context.object
    bpy.ops.object.shade_smooth()

    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 5.0))
    sun = bpy.context.object
    # 정면에서 비스듬히 비춰 화면 안에 명암 경계가 들어오게 한다.
    sun.rotation_euler = (math.radians(60.0), 0.0, math.radians(-30.0))
    sun.data.energy = 5.0
    sun.data.angle = 0.0

    bpy.ops.object.camera_add(location=(0.0, -4.0, 0.0), rotation=(math.radians(90.0), 0.0, 0.0))
    bpy.context.scene.camera = bpy.context.object

    world = bpy.data.worlds.new("CatoonSmokeWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)

    bpy.context.view_layer.objects.active = sphere
    sphere.select_set(True)
    return sphere


def texture_node(material):
    texture_nodes = [
        node for node in material.node_tree.nodes if node.type == "TEX_IMAGE"
    ]
    assert len(texture_nodes) == 1, (
        f"이미지 텍스처 노드 개수가 1이 아닙니다: {len(texture_nodes)}"
    )
    return texture_nodes[0]


def assign_texture(material) -> None:
    image = bpy.data.images.new("CatoonSmokeTexture", width=8, height=8)
    image.generated_color = (*TEXTURE_COLOR, 1.0)
    # sRGB 변환을 거치지 않게 해 렌더 결과와 기준 색을 직접 비교한다.
    image.colorspace_settings.name = "Non-Color"

    texture_node(material).image = image


def configure_render(output_path: Path) -> None:
    scene = bpy.context.scene
    scene.render.engine = eevee_engine()
    scene.render.resolution_x = 200
    scene.render.resolution_y = 200
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.filepath = str(output_path)
    # 선형 EXR로 저장해 색 변환 없이 방출 색을 그대로 읽는다.
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "32"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 8


def dominant_tones(path: Path) -> list[tuple[tuple[float, float, float], int]]:
    """오브젝트 영역의 색을 양자화해 지배적인 톤만 추린다."""
    image = bpy.data.images.load(str(path))
    try:
        pixels = list(image.pixels)
    finally:
        bpy.data.images.remove(image)

    histogram: Counter = Counter()
    total = 0
    for index in range(0, len(pixels), 4):
        red, green, blue, alpha = pixels[index : index + 4]
        if alpha < 0.99:
            continue
        total += 1
        histogram[(round(red, 2), round(green, 2), round(blue, 2))] += 1

    assert total > 500, f"오브젝트 픽셀이 너무 적습니다: {total}"
    # 안티에일리어싱 경계 픽셀을 걸러내기 위해 1% 미만 색은 버린다.
    return [
        (color, count)
        for color, count in histogram.most_common()
        if count >= total * 0.01
    ]


def assert_close(actual, expected, message: str) -> None:
    for left, right in zip(actual, expected):
        assert abs(left - right) < TOLERANCE, f"{message}: {actual} != {expected}"


def assert_two_tones(base_color, label: str) -> None:
    """렌더 결과가 base_color를 살린 밝은 톤과 그림자 톤, 정확히 2톤인지 검사한다."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / "catoon.exr"
        configure_render(output_path)
        bpy.ops.render.render(write_still=True)
        assert output_path.exists(), f"{label}: 렌더 결과가 없습니다: {output_path}"
        tones = dominant_tones(output_path)

    assert len(tones) == 2, (
        f"{label}: 지배적인 톤이 2개가 아닙니다: {[color for color, _ in tones]}"
    )

    expected_shadow = tuple(
        channel * tint for channel, tint in zip(base_color, SHADOW_TINT)
    )
    colors = sorted((color for color, _ in tones), key=sum)
    assert any(channel > 0.01 for channel in colors[1]), (
        f"{label}: 밝은 톤이 검은색입니다: {colors[1]}"
    )
    assert_close(colors[1], base_color, f"{label}: 밝은 톤이 기준 색과 다릅니다")
    assert_close(colors[0], expected_shadow, f"{label}: 그림자 톤이 기대값과 다릅니다")


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    if registered_here:
        addon.register()
    try:
        sphere = build_scene()

        result = bpy.ops.shader.catoon_operator()
        assert result == {"FINISHED"}, f"Catoon 실행 실패: {result}"

        assert len(sphere.data.materials) == 1, (
            f"머티리얼 슬롯 개수가 1이 아닙니다: {len(sphere.data.materials)}"
        )
        material = sphere.data.materials[0]
        assert bpy.data.node_groups.get("CatoonGroup") is not None, (
            "CatoonGroup 노드 그룹이 생성되지 않았습니다."
        )

        # Principled BSDF를 제거하고 Emission 기반 셀셰이딩으로 대체했는지 확인
        group = bpy.data.node_groups["CatoonGroup"]
        group_types = {node.type for node in group.nodes}
        for required in ("SHADERTORGB", "BSDF_DIFFUSE", "EMISSION", "MAP_RANGE"):
            assert required in group_types, f"{required} 노드가 없습니다: {group_types}"
        assert "BSDF_PRINCIPLED" not in {node.type for node in material.node_tree.nodes}, (
            "Principled BSDF가 남아 있습니다."
        )

        # 텍스처를 지정하지 않은 기본 상태. 이미지 없는 텍스처 노드는 검은색으로
        # 평가되므로, 기본 흰색 이미지가 없으면 머티리얼 전체가 검게 나온다.
        base_image = texture_node(material).image
        assert base_image is not None, (
            "기본 이미지가 없어 텍스처를 지정하기 전에는 검은색으로 렌더링됩니다."
        )
        assert_two_tones(
            (1.0, 1.0, 1.0),
            "기본 상태",
        )

        # 사용자 텍스처를 지정한 상태
        assign_texture(material)
        assert_two_tones(TEXTURE_COLOR, "텍스처 지정 상태")
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Catoon 셀셰이딩 Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
