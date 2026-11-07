import ast
import json
import hashlib
import os
import unittest
from types import SimpleNamespace
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

def load_function(name):
    function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"os": os, "Path": Path, "hashlib": hashlib, "json": json, "load_file_content": lambda path: "old_user\nold_password"}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<upstream>", "exec"), namespace)
    return namespace[name]

class QingLongConfigTest(unittest.TestCase):
    def test_cache_open_is_nonblocking_on_posix(self):
        function = load_function("read_cached_state")
        calls = []
        def missing(path, flags):
            calls.append(flags)
            raise FileNotFoundError()
        function.__globals__["open_private_file"] = missing
        function.__globals__["os"] = SimpleNamespace(O_RDONLY=0, O_NONBLOCK=2048)
        self.assertEqual(function(Path('cache.json')), (None, True))
        self.assertEqual(calls, [2048])
    def test_corrupt_cache_is_not_overwritten(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("decode_cached_state", names)
        function = load_function("decode_cached_state")
        self.assertEqual(function('{bad json'), (None, False))
        self.assertEqual(function('{"cookies": [], "origins": []}'), ({"cookies": [], "origins": []}, True))

    def test_account_lock_covers_entire_playwright_run(self):
        main = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        protected = [node for node in ast.walk(main) if isinstance(node, ast.With) and any(isinstance(item.context_expr, ast.Call) and isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == 'account_lock' for item in node.items)]
        self.assertTrue(protected)
        self.assertTrue(any(isinstance(item.context_expr, ast.Call) and isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == 'sync_playwright' for item in protected[0].items))

    def test_browser_rejected_cache_is_preserved_and_falls_back(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("new_context_with_cache", names)
        function = load_function("new_context_with_cache")
        class Browser:
            def new_context(self, storage_state=None):
                if storage_state is not None:
                    raise ValueError("invalid cookie")
                return "fresh"
        self.assertEqual(function(Browser(), {"cookies": [{}], "origins": []}, True), ("fresh", False))

    def test_second_run_for_same_account_is_blocked(self):
        node = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'account_lock')
        namespace = {"os": os, "contextmanager": contextmanager,
                     "open_private_file": lambda path, flags: os.open(__file__, os.O_RDWR)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<upstream>", "exec"), namespace)
        lock = namespace['account_lock']
        with lock(Path('account.json')):
            with self.assertRaisesRegex(RuntimeError, '签到任务在运行'):
                with lock(Path('account.json')):
                    pass
        with lock(Path('account.json')):
            pass
    def test_runtime_directory_must_be_explicit_and_absolute(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("runtime_dir", names)
        function = load_function("runtime_dir")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SAKURAFRP_DATA_DIR"):
                function()
        with patch.dict(os.environ, {"SAKURAFRP_DATA_DIR": "relative"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SAKURAFRP_DATA_DIR"):
                function()
        absolute = Path.cwd()
        with patch.dict(os.environ, {"SAKURAFRP_DATA_DIR": str(absolute)}, clear=True):
            self.assertEqual(function(), absolute)

    def test_main_does_not_delete_old_logs(self):
        main = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        calls = [node.func.id for node in ast.walk(main) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn("clean_old_logs", calls)
    def test_account_state_is_scoped_to_username(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("account_state_file", names)
        function = load_function("account_state_file")
        first = function(Path("private"), "alice")
        self.assertEqual(first, function(Path("private"), "alice"))
        self.assertNotEqual(first, function(Path("private"), "bob"))
        self.assertNotIn("alice", str(first))

    def test_debug_screenshot_switch_controls_writes(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("save_debug_image", names)
        function = load_function("save_debug_image")
        class Sink:
            def __init__(self):
                self.values = []
            def write_bytes(self, data):
                self.values.append(data)
        sink = Sink()
        function(sink, b"image", False)
        self.assertEqual(sink.values, [])
        function(sink, b"image", True)
        self.assertEqual(sink.values, [b"image"])

    def test_login_failure_stops_before_signin(self):
        main = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        found = any(isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.operand, ast.Name) and node.test.operand.id == "is_logged_in" and any(isinstance(child, ast.Raise) for child in ast.walk(node)) for node in ast.walk(main))
        self.assertTrue(found)
    def test_final_captcha_check_detects_late_success(self):
        names = [node.name for node in TREE.body if isinstance(node, ast.FunctionDef)]
        self.assertIn("resolve_sign_success", names)
        function = load_function("resolve_sign_success")
        self.assertTrue(function(None, False, lambda page: object()))
        self.assertFalse(function(None, False, lambda page: None))
        self.assertTrue(function(None, True, lambda page: None))
    def test_credentials_are_read_from_environment(self):
        function = load_function("load_username_password")
        with patch.dict(os.environ, {"SAKURAFRP_USERNAME": "user", "SAKURAFRP_PASSWORD": "secret"}, clear=True):
            self.assertEqual(function(Path("missing-account.txt")), ("user", "secret"))

    def test_missing_credentials_report_names_without_values(self):
        function = load_function("load_username_password")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SAKURAFRP_USERNAME.*SAKURAFRP_PASSWORD"):
                function(Path("missing-account.txt"))

if __name__ == "__main__":
    unittest.main()
