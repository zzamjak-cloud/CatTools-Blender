"""CatTools 배포 구조의 최소 회귀 검사를 수행합니다."""

from __future__ import annotations

import ast
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MANIFEST_PATH = ROOT / "blender_manifest.toml"
PAGES_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pages.yml"
README_PATH = ROOT / "README.md"

EXPECTED_REGISTERED_CLASSES = [
    "OBJECT_PT_WoodyTool",
    "CircleArray",
    "Add_Material",
    "SHADER_OP_Blend2Tex",
    "SHADER_OP_Blend3Tex",
    "SHADER_OP_Blend4Tex",
    "SHADER_OP_TwoSideTex",
    "Add_Lattice",
    "Add_Mirror_X_Modifier",
    "Add_Mirror_Y_Modifier",
    "Add_Mirror_Z_Modifier",
]

EXPECTED_IDNAMES = {
    "OBJECT_PT_WoodyTool": "OBJECT_PT_woodytool",
    "OBJECT_PT_Spacing": "OBJECT_PT_spacing",
    "OBJECT_PT_Mirror_Modifier": "OBJECT_PT_Mirror_Modifier",
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
        self.assertEqual(manifest["version"], "1.0.1")
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
        self.assertEqual(info["version"], (1, 0, 1))
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

    def test_mirror_operators_preserve_positive_side(self) -> None:
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
                self.assertIn(
                    f"-0.01 < vertex.co.{axis} < 0",
                    comparisons,
                )
                self.assertIn(
                    f"vertex.co.{axis} < 0.0",
                    comparisons,
                )

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
        for panel_name in panel_names:
            with self.subTest(panel=panel_name):
                self.assertEqual(
                    assignment_value(self.classes[panel_name], "bl_category"),
                    "CatTools",
                )

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


if __name__ == "__main__":
    unittest.main()
