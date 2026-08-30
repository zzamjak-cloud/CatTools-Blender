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
        self.assertEqual(manifest["version"], "1.0.3")
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
        self.assertEqual(info["version"], (1, 0, 3))
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
