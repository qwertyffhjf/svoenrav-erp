#!/usr/bin/env python3
"""Local SVOENRAV launcher. Standard library only; never starts paid services."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".svoenrav"
COMPOSE = ROOT / "svoenrav" / "compose.yaml"


class UserError(Exception):
	pass


def read_env(path: Path) -> dict[str, str]:
	if not path.exists():
		return {}
	result = {}
	for line in path.read_text(encoding="utf-8").splitlines():
		if not line or line.startswith("#"):
			continue
		key, separator, value = line.partition("=")
		if not separator or not re.fullmatch(r"[A-Z_]+", key):
			raise UserError("Некорректный файл локальных настроек.")
		result[key] = value
	return result


def initialise(state: Path = STATE, *, lan: bool = False, port: int = 8080):
	if not 1024 <= port <= 65535:
		raise UserError("Порт должен быть от 1024 до 65535.")
	state.mkdir(parents=True, exist_ok=True)
	env_path = state / ".env"
	env = read_env(env_path)
	new_installation = not env
	if new_installation:
		if (state / "credentials.txt").exists():
			raise UserError("Найдены прежние реквизиты без файла .env. Восстановите прежние настройки, чтобы сохранить доступ к базе.")
		env = {"DB_ROOT_PASSWORD": secrets.token_hex(24), "ADMIN_PASSWORD": secrets.token_hex(18)}
	elif not env.get("DB_ROOT_PASSWORD") or not env.get("ADMIN_PASSWORD"):
		raise UserError("В локальных настройках отсутствуют пароли. Сначала восстановите прежний файл .env.")
	env.update({"HOST_BIND": "0.0.0.0" if lan else "127.0.0.1", "HTTP_PORT": str(port)})
	text = "".join(f"{key}={value}\n" for key, value in env.items())
	temporary = state / f".env.{os.getpid()}.new"
	fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as handle:
		handle.write(text)
	os.replace(temporary, env_path)
	if os.name != "nt":
		env_path.chmod(0o600)
	if not (state / "credentials.txt").exists():
		credentials = state / "credentials.txt"
		fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "w", encoding="utf-8") as handle:
			handle.write("SVOENRAV ERP\nЛогин: Administrator\nНачальный пароль: " + env["ADMIN_PASSWORD"] + "\n")
	return env


def compose_command(state: Path = STATE, compose: Path = COMPOSE):
	return ["docker", "compose", "--project-name", "svoenrav", "--env-file", str(state / ".env"), "-f", str(compose)]


def run(arguments, *, capture=False):
	return subprocess.run(arguments, cwd=ROOT, check=True, text=True, capture_output=capture)


def require_docker():
	if not shutil.which("docker"):
		raise UserError("Docker не найден. Нужны Docker Engine и Docker Compose. Инструкция: README_SVOENRAV.md.")
	try:
		run(["docker", "compose", "version"], capture=True)
		run(["docker", "info"], capture=True)
	except subprocess.CalledProcessError as exc:
		raise UserError("Docker Compose недоступен или Docker не запущен.") from exc


def check_source(root: Path = ROOT):
	metadata = json.loads((root / "svoenrav" / "upstream.json").read_text(encoding="utf-8"))
	version_text = (root / "erpnext" / "__init__.py").read_text(encoding="utf-8")
	match = re.search(r'^__version__ = "([^"]+)"', version_text, re.MULTILINE)
	if not match or match.group(1) != metadata["erpnext"]["version"]:
		raise UserError("Версия исходников отличается от зафиксированной версии базового образа.")
	modules = (root / "erpnext" / "modules.txt").read_text(encoding="utf-8").splitlines()
	for required in ("SVOENRAV", "Manufacturing", "Stock", "Accounts", "Buying", "Selling"):
		if required not in modules:
			raise UserError("Отсутствует модуль " + required)
	settings = json.loads((root / "erpnext/svoenrav/doctype/svoenrav_settings/svoenrav_settings.json").read_text(encoding="utf-8"))
	if not settings.get("issingle") or settings["module"] != "SVOENRAV":
		raise UserError("Некорректное описание настроек SVOENRAV.")
	license_text = (root / "license.txt").read_text(encoding="utf-8")
	if "GNU GENERAL PUBLIC LICENSE" not in license_text or "Version 3" not in license_text:
		raise UserError("Не найдена исходная лицензия ERPNext.")
	return match.group(1)


def parse_container_rows(output):
	output = output.strip()
	if not output:
		return []
	if output.startswith("["):
		return json.loads(output)
	return [json.loads(line) for line in output.splitlines() if line.strip()]


def wait_for_site(command, *, timeout=900):
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		result = run(command + ["ps", "--all", "--format", "json", "create-site"], capture=True)
		for row in parse_container_rows(result.stdout):
			if row.get("State") == "exited":
				if int(row.get("ExitCode", 1)) == 0:
					return
				raise UserError("Создание базы завершилось с ошибкой. Посмотрите python tools/svoenrav.py logs.")
		time.sleep(2)
	raise UserError("Создание базы ещё не завершено. Состояние: python tools/svoenrav.py status.")


def wait_for_http(port, *, timeout=90):
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			with urllib.request.urlopen(f"http://127.0.0.1:{port}/login", timeout=3) as response:
				if response.status == 200:
					return
		except (urllib.error.URLError, TimeoutError, ConnectionError):
			pass
		time.sleep(2)
	raise UserError("База создана, веб-интерфейс ещё не ответил. Посмотрите журналы запуска.")


def main(argv=None):
	parser = argparse.ArgumentParser(description="Локальный запуск SVOENRAV ERP")
	parser.add_argument("action", choices=["start", "stop", "status", "logs", "backup", "check"])
	parser.add_argument("--lan", action="store_true", help="Разрешить доступ из локальной сети")
	parser.add_argument("--port", type=int, default=8080)
	parser.add_argument("--source-only", action="store_true", help="Проверить исходники без Docker")
	args = parser.parse_args(argv)
	try:
		version = check_source()
		if args.action == "check":
			if not args.source_only:
				require_docker()
			print(f"Исходники SVOENRAV / ERPNext {version}: OK")
			return 0
		require_docker()
		command = compose_command()
		if args.action == "start":
			if not (STATE / ".env").exists():
				volume = subprocess.run(["docker", "volume", "inspect", "svoenrav_db-data"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				if volume.returncode == 0:
					raise UserError("Найдена существующая база, но нет её локальных настроек. Восстановите .svoenrav/.env.")
			initialise(lan=args.lan, port=args.port)
			run(command + ["build", "backend"])
			run(command + ["up", "-d", "--no-build"])
			print("Ожидание создания базы и запуска интерфейса…", flush=True)
			wait_for_site(command)
			wait_for_http(args.port)
			print(f"Открыть: http://localhost:{args.port}/svoenrav")
			print("Логин: Administrator. Начальный пароль: .svoenrav/credentials.txt")
			if args.lan:
				print(f"Телефон в той же сети: http://IP-компьютера:{args.port}/svoenrav")
			return 0
		if not (STATE / ".env").exists():
			raise UserError("Система ещё не инициализирована. Выполните start.")
		if args.action == "stop":
			run(command + ["down"])
		elif args.action == "status":
			run(command + ["ps", "--all"])
		elif args.action == "logs":
			run(command + ["logs", "--tail", "100", "create-site", "backend", "frontend"])
		elif args.action == "backup":
			run(command + ["exec", "-T", "backend", "bench", "--site", "frontend", "backup", "--with-files"])
			destination = STATE / "backups"
			destination.mkdir(exist_ok=True)
			run(command + ["cp", "backend:/home/frappe/frappe-bench/sites/frontend/private/backups/.", str(destination)])
			print("Резервная копия: .svoenrav/backups")
		return 0
	except (UserError, OSError, ValueError, subprocess.CalledProcessError) as exc:
		print(str(exc), file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
