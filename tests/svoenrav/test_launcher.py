import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("svoenrav_launcher", ROOT / "tools/svoenrav.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
	def test_passwords_persist_and_stay_private(self):
		with tempfile.TemporaryDirectory() as folder:
			state = Path(folder)
			first = launcher.initialise(state)
			second = launcher.initialise(state, lan=True, port=8090)
			self.assertEqual(first["ADMIN_PASSWORD"], second["ADMIN_PASSWORD"])
			self.assertEqual(first["DB_ROOT_PASSWORD"], second["DB_ROOT_PASSWORD"])
			self.assertNotEqual(first["ADMIN_PASSWORD"], first["DB_ROOT_PASSWORD"])
			self.assertNotEqual(first["ADMIN_PASSWORD"], "admin")
			self.assertEqual(first["HOST_BIND"], "127.0.0.1")
			self.assertEqual(second["HOST_BIND"], "0.0.0.0")
			if os.name != "nt":
				self.assertEqual((state / ".env").stat().st_mode & 0o777, 0o600)
				self.assertEqual((state / "credentials.txt").stat().st_mode & 0o777, 0o600)

	def test_broken_existing_state_does_not_generate_new_password(self):
		with tempfile.TemporaryDirectory() as folder:
			state = Path(folder)
			(state / ".env").write_text("HOST_BIND=127.0.0.1\n", encoding="utf-8")
			with self.assertRaises(launcher.UserError):
				launcher.initialise(state)
			self.assertFalse((state / "credentials.txt").exists())

	def test_invalid_port(self):
		with tempfile.TemporaryDirectory() as folder:
			for port in [0, -1, 80, 65536]:
				with self.subTest(port=port), self.assertRaises(launcher.UserError):
					launcher.initialise(Path(folder), port=port)

	def test_existing_credentials_without_env_are_not_replaced(self):
		with tempfile.TemporaryDirectory() as folder:
			state = Path(folder)
			(state / "credentials.txt").write_text("existing credentials", encoding="utf-8")
			with self.assertRaises(launcher.UserError):
				launcher.initialise(state)
			self.assertFalse((state / ".env").exists())
			self.assertEqual((state / "credentials.txt").read_text(), "existing credentials")

	def test_compose_handles_spaces_without_shell(self):
		args = launcher.compose_command(Path("/tmp/my workshop"), Path("/tmp/my workshop/compose.yaml"))
		self.assertIn("/tmp/my workshop/.env", args)
		self.assertIn("/tmp/my workshop/compose.yaml", args)
		self.assertNotIn("-v", args)

	def test_compose_json_formats(self):
		for output in ['[{"State":"exited","ExitCode":0}]', '{"State":"exited","ExitCode":0}\n']:
			self.assertEqual(launcher.parse_container_rows(output)[0]["ExitCode"], 0)
		self.assertEqual(launcher.parse_container_rows(""), [])

	def test_bootstrap_success_and_failure(self):
		with patch.object(launcher, "run", return_value=SimpleNamespace(stdout='{"State":"exited","ExitCode":0}')):
			launcher.wait_for_site(["docker", "compose"])
		with patch.object(launcher, "run", return_value=SimpleNamespace(stdout='{"State":"exited","ExitCode":1}')):
			with self.assertRaises(launcher.UserError):
				launcher.wait_for_site(["docker", "compose"])

	def test_real_source_and_licence(self):
		self.assertEqual(launcher.check_source(), "16.53.0")
