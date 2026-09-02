"""CatTools 배포 구조의 최소 회귀 검사를 수행합니다."""

from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MANIFEST_PATH = ROOT / "blender_manifest.toml"
PAGES_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pages.yml"
README_PATH = ROOT / "README.md"
DEV_RUN_PATH = ROOT / "scripts" / "dev_run.sh"
WINDOWS_DEV_RUN_PATH = ROOT / "scripts" / "dev_run.ps1"
WINDOWS_DEV_WRAPPER_PATH = ROOT / "scripts" / "dev_run.bat"
DEV_BOOTSTRAP_PATH = ROOT / "scripts" / "dev_bootstrap.py"
SORT_REPOSITORY_INDEX_PATH = ROOT / "scripts" / "sort_repository_index.py"
DEV_PROFILE_SMOKE_PATH = ROOT / "tests" / "blender_dev_profile_smoke.py"
MIRROR_SMOKE_PATH = ROOT / "tests" / "blender_mirror_smoke.py"
ALIGN_SMOKE_PATH = ROOT / "tests" / "blender_align_smoke.py"
CATOON_SMOKE_PATH = ROOT / "tests" / "blender_catoon_smoke.py"
SIDEBAR_SMOKE_PATH = ROOT / "tests" / "blender_sidebar_smoke.py"

EXPECTED_REGISTERED_CLASSES = [
    "OBJECT_PT_WoodyTool",
    "VIEW3D_OT_CatSidebar",
    "OBJECT_OT_CatAlign",
    "CircleArray",
    "Add_Material",
    "SHADER_OP_Blend2Tex",
    "SHADER_OP_Blend3Tex",
    "SHADER_OP_Blend4Tex",
    "SHADER_OP_TwoSideTex",
    "SHADER_OP_Catoon",
    "Add_Lattice",
    "Add_Mirror_X_Modifier",
    "Add_Mirror_Y_Modifier",
    "Add_Mirror_Z_Modifier",
]

EXPECTED_IDNAMES = {
    "OBJECT_PT_WoodyTool": "OBJECT_PT_woodytool",
    "OBJECT_PT_Spacing": "OBJECT_PT_spacing",
    "OBJECT_PT_Mirror_Modifier": "OBJECT_PT_Mirror_Modifier",
    "OBJECT_OT_CatAlign": "object.cat_align",
    "VIEW3D_OT_CatSidebar": "view3d.cat_toggle_sidebar",
    "Add_Cylinder_6": "wm.add_cylinder_6",
    "Add_Cylinder_8": "wm.add_cylinder_8",
    "Add_Cylinder_10": "wm.add_cylinder_10",
    "Add_Cylinder_12": "wm.add_cylinder_12",
    "CircleArray": "object.circle_array",
    "Add_Material": "wm.add_material",
    "SHADER_OP_Blend2Tex": "shader.blend2tex_operator",
    "SHADER_OP_Blend3Tex": "shader.blend3tex_operator",
    "SHADER_OP_Blend4Tex": "shader.blend4tex_operator",
    "SHADER_OP_TwoSideTex": "shader.twosidetex_operator",
    "SHADER_OP_Catoon": "shader.catoon_operator",
    "PALETTE_OP_RGB": "palette.rgb_operator",
    "Add_Lattice": "wm.add_lattice",
    "Add_Text": "wm.add_text",
    "Add_Mirror_X_Modifier": "wm.add_mirror_x_modifier",
    "Add_Mirror_Y_Modifier": "wm.add_mirror_y_modifier",
    "Add_Mirror_Z_Modifier": "wm.add_mirror_z_modifier",
}

MIRROR_AXES = {
    "Add_Mirror_X_Modifier": "x",
    "Add_Mirror_Y_Modifier": "y",
    "Add_Mirror_Z_Modifier": "z",
}


def assignment_value(node: ast.ClassDef, name: str):
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"{node.name}.{name}을 찾을 수 없습니다.")


def assignment_name(node: ast.ClassDef, name: str) -> str:
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            if not isinstance(statement.value, ast.Name):
                raise AssertionError(f"{node.name}.{name}이 이름 참조가 아닙니다.")
            return statement.value.id
    raise AssertionError(f"{node.name}.{name}을 찾을 수 없습니다.")


def module_constant(tree: ast.Module, name: str):
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"모듈 상수 {name}을 찾을 수 없습니다.")


class CatToolsSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ADDON_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(ADDON_PATH))
        cls.classes = {
            node.name: node for node in cls.tree.body if isinstance(node, ast.ClassDef)
        }

    def test_python_syntax(self) -> None:
        compile(self.source, str(ADDON_PATH), "exec")

    def test_manifest_metadata(self) -> None:
        manifest = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["id"], "cat_tools")
        self.assertEqual(manifest["name"], "CatTools")
        self.assertEqual(manifest["version"], "1.2.0")
        self.assertEqual(manifest["blender_version_min"], "4.2.0")
        self.assertIn("SPDX:GPL-3.0-or-later", manifest["license"])

    def test_bl_info_metadata(self) -> None:
        info_node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets)
        )
        info = ast.literal_eval(info_node.value)
        self.assertEqual(info["name"], "CatTools")
        self.assertEqual(info["version"], (1, 2, 0))
        self.assertEqual(info["blender"], (4, 2, 0))

    def test_registered_class_order(self) -> None:
        classes_node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "classes" for target in node.targets)
        )
        registered = [element.id for element in classes_node.value.elts]
        self.assertEqual(registered, EXPECTED_REGISTERED_CLASSES)

    def test_legacy_idnames_are_preserved(self) -> None:
        actual = {
            class_name: assignment_value(self.classes[class_name], "bl_idname")
            for class_name in EXPECTED_IDNAMES
        }
        self.assertEqual(actual, EXPECTED_IDNAMES)

    def test_mirror_operators_preserve_expected_side(self) -> None:
        for class_name, axis in MIRROR_AXES.items():
            with self.subTest(axis=axis):
                operator = self.classes[class_name]
                execute = next(
                    node
                    for node in operator.body
                    if isinstance(node, ast.FunctionDef) and node.name == "execute"
                )
                comparisons = {
                    ast.unparse(node)
                    for node in ast.walk(execute)
                    if isinstance(node, ast.Compare)
                }
                if class_name == "Add_Mirror_X_Modifier":
                    self.assertIn("0 < vertex.co.x < 0.01", comparisons)
                    self.assertIn("vertex.co.x > 0.0", comparisons)
                else:
                    self.assertIn(f"-0.01 < vertex.co.{axis} < 0", comparisons)
                    self.assertIn(f"vertex.co.{axis} < 0.0", comparisons)

    def test_mirror_delete_is_guarded_when_side_is_empty(self) -> None:
        for class_name in MIRROR_AXES:
            with self.subTest(operator=class_name):
                operator = self.classes[class_name]
                execute = next(
                    node
                    for node in operator.body
                    if isinstance(node, ast.FunctionDef) and node.name == "execute"
                )
                guard = next(
                    node
                    for node in ast.walk(execute)
                    if isinstance(node, ast.If)
                    and isinstance(node.test, ast.Name)
                    and node.test.id == "vertices_to_delete"
                )
                delete_call = next(
                    node
                    for node in ast.walk(guard)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "delete"
                )
                geom_keyword = next(
                    keyword
                    for keyword in delete_call.keywords
                    if keyword.arg == "geom"
                )
                self.assertIsInstance(geom_keyword.value, ast.Name)
                self.assertEqual(geom_keyword.value.id, "vertices_to_delete")

    def test_panel_branding(self) -> None:
        main_panel = self.classes["OBJECT_PT_WoodyTool"]
        self.assertEqual(assignment_value(main_panel, "bl_label"), "CatTools")
        panel_names = [
            "OBJECT_PT_WoodyTool",
            "OBJECT_PT_Spacing",
            "OBJECT_PT_Mirror_Modifier",
        ]
        self.assertEqual(module_constant(self.tree, "CAT_CATEGORY"), "CatTools")
        for panel_name in panel_names:
            with self.subTest(panel=panel_name):
                self.assertEqual(
                    assignment_name(self.classes[panel_name], "bl_category"),
                    "CAT_CATEGORY",
                )

    def test_transform_and_align_row_tables(self) -> None:
        wanted = {
            "TRANSFORM_ROWS",
            "ALIGN_ROWS",
            "ALIGN_BUTTONS",
            "ALIGN_AXIS_INDICES",
            "ALIGN_PROPERTIES",
            "TRANSFORM_LABEL_UNITS",
            "TRANSFORM_COMPACT_LABEL_UNITS",
            "TRANSFORM_COMPACT_WIDTH",
        }
        tables = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in wanted
        }
        self.assertEqual(set(tables), wanted)
        self.assertEqual(
            tables["TRANSFORM_ROWS"],
            (
                ("Loc", "L", "location"),
                ("Rot", "R", "rotation_euler"),
                ("Sca", "S", "scale"),
            ),
        )
        self.assertEqual(
            tables["ALIGN_ROWS"],
            (
                ("Loc", "L", "LOCATION"),
                ("Rot", "R", "ROTATION"),
                ("Sca", "S", "SCALE"),
            ),
        )
        # 축약 라벨 칸은 기본 칸보다 좁아야 하고, 기본 사이드바 폭(약 280)에서는
        # 축약되지 않아야 한다.
        self.assertLess(
            tables["TRANSFORM_COMPACT_LABEL_UNITS"],
            tables["TRANSFORM_LABEL_UNITS"],
        )
        self.assertLess(tables["TRANSFORM_COMPACT_WIDTH"], 280)
        self.assertEqual(
            tables["ALIGN_BUTTONS"],
            (("X", "X"), ("Y", "Y"), ("Z", "Z"), ("ALL", "All")),
        )
        self.assertEqual(tables["ALIGN_AXIS_INDICES"], {"X": 0, "Y": 1, "Z": 2})
        self.assertEqual(
            tables["ALIGN_PROPERTIES"],
            {
                "LOCATION": "location",
                "ROTATION": "rotation_euler",
                "SCALE": "scale",
            },
        )

    def test_transform_and_align_use_single_line_three_column_grid(self) -> None:
        panel = self.classes["OBJECT_PT_WoodyTool"]
        draw = next(
            node
            for node in panel.body
            if isinstance(node, ast.FunctionDef) and node.name == "draw"
        )
        source = ast.unparse(draw)
        # 축별 필드를 index 인자로 따로 배치해야 세로 3줄이 아닌 한 줄 3열이 된다.
        self.assertIn(
            "fields.prop(selected_object, property_name, index=index, text='')",
            source,
        )
        # 라벨 칸은 비율 분할이 아닌 고정 폭이어야 사이드바를 넓혀도 여백이 벌어지지 않는다.
        self.assertNotIn("column.split(", source)
        self.assertEqual(source.count("label_column.ui_units_x = label_units"), 2)
        self.assertEqual(
            source.count("label_column.label(text=short_label if compact else full_label)"),
            2,
        )
        self.assertIn("compact, label_units = transform_label_metrics(context)", source)
        self.assertIn("operator.mode = align_mode", source)
        self.assertIn("operator.axis = axis", source)

    def test_label_metrics_shrinks_labels_on_narrow_sidebar(self) -> None:
        helper = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "transform_label_metrics"
        )
        source = ast.unparse(helper)
        # ui_scale로 나눠 논리 폭을 기준으로 판단해야 HiDPI에서 항상 축약되지 않는다.
        self.assertIn("region.width / ui_scale < TRANSFORM_COMPACT_WIDTH", source)
        self.assertIn("return (True, TRANSFORM_COMPACT_LABEL_UNITS)", source)
        self.assertIn("return (False, TRANSFORM_LABEL_UNITS)", source)
        # region이 없는 컨텍스트에서 draw가 깨지지 않아야 한다.
        self.assertIn("if region is None", source)

    def test_align_operator_contract(self) -> None:
        operator = self.classes["OBJECT_OT_CatAlign"]
        self.assertEqual(assignment_value(operator, "bl_options"), {"REGISTER", "UNDO"})

        annotations = {
            statement.target.id: ast.unparse(statement.annotation)
            for statement in operator.body
            if isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
        }
        self.assertEqual(set(annotations), {"mode", "axis"})
        for name, annotation in annotations.items():
            with self.subTest(property=name):
                self.assertTrue(annotation.startswith("EnumProperty("), annotation)

        execute = next(
            node
            for node in operator.body
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        source = ast.unparse(execute)
        # 활성 오브젝트는 기준이므로 정렬 대상에서 제외되어야 한다.
        self.assertIn("obj is not active_object", source)
        # ALL은 세 축 모두, 단일 축은 해당 인덱스만 대상으로 한다.
        self.assertIn("(0, 1, 2) if self.axis == 'ALL' else (ALIGN_AXIS_INDICES[self.axis],)", source)
        # 비오일러 rotation_mode에서 회전 정렬이 조용히 무시되지 않도록 환산한다.
        self.assertIn("rotation_as_euler(", source)
        self.assertIn("apply_rotation_euler(obj, euler)", source)

    def test_align_rotation_mode_helpers_cover_every_rotation_mode(self) -> None:
        helpers = {
            node.name: ast.unparse(node)
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"rotation_as_euler", "apply_rotation_euler"}
        }
        self.assertEqual(set(helpers), {"rotation_as_euler", "apply_rotation_euler"})
        for name, source in helpers.items():
            with self.subTest(helper=name):
                self.assertIn("'QUATERNION'", source)
                self.assertIn("'AXIS_ANGLE'", source)
                self.assertIn("rotation_axis_angle", source)

    def test_align_runtime_smoke_uses_enabled_development_extension(self) -> None:
        source = ALIGN_SMOKE_PATH.read_text(encoding="utf-8")
        compile(source, str(ALIGN_SMOKE_PATH), "exec")
        self.assertIn("importlib.import_module(MODULE_NAME)", source)
        self.assertIn("registered_here", source)
        self.assertIn("bpy.ops.object.cat_align(mode=mode, axis=axis)", source)
        self.assertIn("bpy.ops.object.cat_align.poll()", source)
        self.assertIn("rotation_mode = \"QUATERNION\"", source)

    def test_catoon_cel_shading_contract(self) -> None:
        sockets = next(
            ast.literal_eval(node.value)
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CATOON_SOCKETS"
        )
        defaults = {name: value for name, _socket_type, value in sockets}
        # 밝은 면이 텍스처 색을 그대로 살리려면 Light Color가 흰색이어야 한다.
        self.assertEqual(defaults["Light Color"], (1.0, 1.0, 1.0, 1.0))
        # 그림자 톤은 텍스처에 곱해지므로 1보다 어두워야 만화적 음영이 된다.
        self.assertTrue(all(channel < 1.0 for channel in defaults["Shadow Color"][:3]))
        self.assertEqual(defaults["Threshold"], 0.5)
        self.assertEqual(defaults["Softness"], 0.0)

        operator = self.classes["SHADER_OP_Catoon"]
        self.assertEqual(assignment_value(operator, "bl_label"), "Catoon")
        execute = next(
            node
            for node in operator.body
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        source = ast.unparse(execute)
        # 2톤 셀셰이딩 핵심 노드
        for node_type in (
            "ShaderNodeShaderToRGB",
            "ShaderNodeBsdfDiffuse",
            "ShaderNodeRGBToBW",
            "ShaderNodeMapRange",
            "ShaderNodeEmission",
        ):
            with self.subTest(node=node_type):
                self.assertIn(node_type, source)
        # Principled BSDF를 제거하고 Emission 기반으로 대체해야 평면적인 만화 음영이 된다.
        self.assertIn("nodes.remove(nodes.get('Principled BSDF'))", source)
        # 인스턴스 소켓에 기본값을 넣지 않으면 노드 그룹이 검은색으로 시작한다.
        self.assertIn(
            "node_group.inputs[socket_name].default_value = default_value",
            source,
        )
        # 중복 이름 소켓 때문에 이름/인덱스 대신 활성 소켓으로 연결해야 한다.
        self.assertIn("enabled_socket(", source)
        # 이미지 없는 텍스처 노드는 검은색으로 평가되므로 흰색 기본 이미지가 필요하다.
        self.assertIn("node_TexImage.image = catoon_base_image()", source)

    def test_catoon_base_image_prevents_black_material(self) -> None:
        helper = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "catoon_base_image"
        )
        source = ast.unparse(helper)
        self.assertIn("generated_color = (1.0, 1.0, 1.0, 1.0)", source)
        # 같은 이름의 데이터블록이 파일 기반 이미지로 바뀐 경우에는 재사용하지 않는다.
        self.assertIn("image.source != 'GENERATED'", source)

    def test_catoon_button_is_exposed_in_shader_row(self) -> None:
        panel = self.classes["OBJECT_PT_WoodyTool"]
        draw = next(
            node
            for node in panel.body
            if isinstance(node, ast.FunctionDef) and node.name == "draw"
        )
        self.assertIn(
            "row.operator(SHADER_OP_Catoon.bl_idname, text=SHADER_OP_Catoon.bl_label)",
            ast.unparse(draw),
        )

    def test_catoon_runtime_smoke_renders_two_tones(self) -> None:
        source = CATOON_SMOKE_PATH.read_text(encoding="utf-8")
        compile(source, str(CATOON_SMOKE_PATH), "exec")
        self.assertIn("importlib.import_module(MODULE_NAME)", source)
        self.assertIn("registered_here", source)
        self.assertIn("bpy.ops.shader.catoon_operator()", source)
        # 색 변환 없이 방출 색을 그대로 읽어야 톤을 정확히 비교할 수 있다.
        self.assertIn('"OPEN_EXR"', source)
        self.assertIn('"Non-Color"', source)
        self.assertIn("assert len(tones) == 2", source)

    def test_sidebar_shortcut_contract(self) -> None:
        operator = self.classes["VIEW3D_OT_CatSidebar"]
        self.assertEqual(
            assignment_value(operator, "bl_idname"), "view3d.cat_toggle_sidebar"
        )
        # 사이드바 토글은 컨텍스트 오버라이드에서도 양방향으로 동작하는
        # region_toggle을 사용해야 한다.
        self.assertIn("bpy.ops.screen.region_toggle(region_type='UI')", self.source)
        self.assertIn("region.active_panel_category = CAT_CATEGORY", self.source)

        # N 키를 애드온 키맵의 3D View 항목에 연결한다.
        self.assertIn("keyconfigs.addon", self.source)
        self.assertIn("""keymaps.new(name="3D View", space_type='VIEW_3D')""", self.source)
        self.assertIn(
            "keymap_items.new(VIEW3D_OT_CatSidebar.bl_idname, 'N', 'PRESS')", self.source
        )

        # 사이드바를 여는 프레임에는 탭 목록이 없어 대입이 거부되므로 재시도한다.
        self.assertIn("(AttributeError, TypeError, ValueError)", self.source)
        self.assertIn("bpy.app.timers.register(_activate_cat_tab_timer", self.source)

        # 해제 시 단축키, 핸들러, 타이머를 모두 되돌린다.
        for cleanup in (
            "unregister_keymaps()",
            "bpy.app.handlers.load_post.remove(_on_load_post)",
            "bpy.app.timers.unregister(_activate_cat_tab_timer)",
        ):
            with self.subTest(cleanup=cleanup):
                self.assertIn(cleanup, self.source)

    def test_sidebar_runtime_smoke_requires_drawn_window(self) -> None:
        source = SIDEBAR_SMOKE_PATH.read_text(encoding="utf-8")
        compile(source, str(SIDEBAR_SMOKE_PATH), "exec")
        self.assertIn("importlib.import_module(MODULE_NAME)", source)
        self.assertIn("registered_here", source)
        self.assertIn("bpy.ops.view3d.cat_toggle_sidebar()", source)
        # 탭 목록은 그리기 이후 생성되므로 창을 강제로 한 프레임 그린다.
        self.assertIn('bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)', source)
        self.assertIn("region.active_panel_category == addon.CAT_CATEGORY", source)
        self.assertIn("addon._on_load_post(None)", source)
        self.assertIn("해제 후에도 단축키가 남아 있습니다", source)

    def test_remote_repository_distribution(self) -> None:
        workflow = PAGES_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn('workflows: ["릴리스"]', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('test("^cat_tools-v.*\\\\.zip$")', workflow)
        self.assertIn(
            '"${blender_binary}" --command extension server-generate '
            "--repo-dir=site --html",
            workflow,
        )
        self.assertIn(
            "python3 scripts/sort_repository_index.py site/index.json",
            workflow,
        )
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn(
            "actions/upload-pages-artifact@"
            "fc324d3547104276b827a68afc52ff2a11cc49c9",
            workflow,
        )
        self.assertIn(
            "actions/deploy-pages@"
            "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
            workflow,
        )

    def test_remote_repository_installation_guide(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "https://zzamjak-cloud.github.io/CatTools-Blender/index.json",
            readme,
        )
        self.assertIn("Check for Updates on Startup", readme)
        self.assertNotIn("Install from Disk", readme)

    def test_repository_index_keeps_only_latest_version_per_addon(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "sort_repository_index",
            SORT_REPOSITORY_INDEX_PATH,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "data": [
                            {"id": "cat_tools", "version": "1.0.2"},
                            {"id": "cat_tools", "version": "1.0.0"},
                            {"id": "cat_tools", "version": "1.0.10"},
                            {"id": "cat_tools", "version": "1.0.1"},
                            {"id": "another_tool", "version": "2.0.0"},
                            {"id": "another_tool", "version": "1.0.0"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            module.sort_index(index_path)
            entries = {
                item["id"]: item["version"]
                for item in json.loads(index_path.read_text(encoding="utf-8"))["data"]
            }
        self.assertEqual(entries, {"another_tool": "2.0.0", "cat_tools": "1.0.10"})

    def test_isolated_development_runner(self) -> None:
        script = DEV_RUN_PATH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", script)
        self.assertIn("CatToolsBlenderDev", script)
        self.assertIn('BLENDER_USER_RESOURCES="$PROFILE"', script)
        self.assertIn('export BLENDER_VERSION', script)
        self.assertIn('export CATTOOLS_DEV_PROFILE_BASE="$PROFILE_BASE"', script)
        self.assertIn('extensions/user_default', script)
        self.assertIn('ADDON_LINK="$EXTENSION_DIR/cat_tools"', script)
        self.assertIn('[[ ! -x "$BLENDER_BIN" ]]', script)
        self.assertIn('ln -sfn "$REPO_ROOT" "$ADDON_LINK"', script)
        self.assertIn(
            '--background --python-exit-code 1 --python "$BOOTSTRAP_SCRIPT"',
            script,
        )
        self.assertIn('exec "$BLENDER_BIN" --python-exit-code 1 "$@"', script)

    def test_development_bootstrap_and_runtime_smoke_syntax(self) -> None:
        bootstrap = DEV_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        runtime_smoke = DEV_PROFILE_SMOKE_PATH.read_text(encoding="utf-8")
        bootstrap_tree = ast.parse(bootstrap, filename=str(DEV_BOOTSTRAP_PATH))
        compile(runtime_smoke, str(DEV_PROFILE_SMOKE_PATH), "exec")
        self.assertIn('MODULE_NAME = "bl_ext.user_default.cat_tools"', bootstrap)
        self.assertIn("bpy.ops.preferences.addon_enable", bootstrap)
        self.assertIn("bpy.ops.wm.save_userpref()", bootstrap)

        main_node = next(
            node
            for node in bootstrap_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        enable_guard = next(
            node
            for node in main_node.body
            if isinstance(node, ast.If)
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "addon_enable"
                for child in ast.walk(node)
            )
        )
        save_calls = [
            child
            for child in ast.walk(main_node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "save_userpref"
        ]
        self.assertEqual(len(save_calls), 1)
        self.assertIn(save_calls[0], list(ast.walk(enable_guard)))

        self.assertIn("BLENDER_USER_RESOURCES", runtime_smoke)
        self.assertIn("addon_link.is_symlink()", runtime_smoke)
        self.assertIn("profile != default_profile", runtime_smoke)
        self.assertIn('"woody" in module_name.lower()', runtime_smoke)

    def test_windows_portable_development_runner(self) -> None:
        self.assertTrue(
            WINDOWS_DEV_RUN_PATH.read_bytes().startswith(b"\xef\xbb\xbf"),
            "Windows PowerShell 5.1 호환을 위해 UTF-8 BOM이 필요합니다.",
        )
        script = WINDOWS_DEV_RUN_PATH.read_text(encoding="utf-8-sig")
        wrapper = WINDOWS_DEV_WRAPPER_PATH.read_text(encoding="utf-8")

        self.assertIn('[string]$BlenderDir = "D:\\Tools\\Blender-5.2-CatToolsDev"', script)
        self.assertIn("$AddonId = 'cat_tools'", script)
        self.assertIn("$ModuleName = 'bl_ext.user_default.cat_tools'", script)
        self.assertIn("Join-Path $BlenderDir 'portable'", script)
        self.assertIn("'extensions\\user_default'", script)
        self.assertIn("New-Item -ItemType Junction", script)
        self.assertIn("@('Junction', 'SymbolicLink')", script)
        self.assertIn("if ($ExistingItem.PSIsContainer)", script)
        self.assertIn("[System.IO.Directory]::Delete($AddonLink, $false)", script)
        self.assertIn("[System.IO.File]::Delete($AddonLink)", script)
        self.assertIn("사용자 파일을 보호하기 위해 자동으로 삭제하지 않습니다.", script)
        self.assertIn("[switch]$LinkOnly", script)
        self.assertIn("[switch]$Background", script)
        self.assertIn("[string]$PythonExpr", script)
        self.assertIn("[string]$PythonFile", script)
        self.assertIn("@('--python-exit-code', '1')", script)
        self.assertIn("@('--python', $BootstrapScript)", script)
        self.assertIn("& $BlenderExecutable @BlenderArguments", script)

        self.assertIn("powershell -NoProfile -ExecutionPolicy Bypass", wrapper)
        self.assertIn('"%~dp0dev_run.ps1" %*', wrapper)
        self.assertIn("exit /b %ERRORLEVEL%", wrapper)

    def test_mirror_smoke_uses_enabled_development_extension(self) -> None:
        source = MIRROR_SMOKE_PATH.read_text(encoding="utf-8")
        compile(source, str(MIRROR_SMOKE_PATH), "exec")
        self.assertIn("importlib.import_module(MODULE_NAME)", source)
        self.assertIn("registered_here", source)
        self.assertIn("bpy.ops.preferences.addon_disable", source)
        self.assertIn("bpy.ops.preferences.addon_enable", source)

    def test_isolated_development_guide(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("CatToolsBlenderDev/<Blender 버전>", readme)
        self.assertIn("./scripts/dev_run.sh", readme)
        self.assertIn("BLENDER_VERSION=5.3", readme)
        self.assertIn("BLENDER_BIN=", readme)
        self.assertIn(
            "--background --python tests/blender_dev_profile_smoke.py",
            readme,
        )
        self.assertIn("D:\\Tools\\Blender-5.2-CatToolsDev", readme)
        self.assertIn(".\\scripts\\dev_run.ps1 -LinkOnly", readme)
        self.assertIn("-Background -PythonFile", readme)
        self.assertIn(".\\scripts\\dev_run.bat", readme)


if __name__ == "__main__":
    unittest.main()
