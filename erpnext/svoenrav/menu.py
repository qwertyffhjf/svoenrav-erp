# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt
"""Menu definitions are data, never executable code or arbitrary URLs."""

import json
import re
from copy import deepcopy

from erpnext.svoenrav.flow import OPERATIONS

# Only these harmless document presets may be placed in a link. No company,
# warehouse, amount, status or permission flags may be supplied by menu JSON.
STOCK_ENTRY_PRESETS = {"Material Issue", "Material Receipt", "Material Transfer"}

DEFAULT_ACTIONS = (
	{"label": "Новый заказ", "description": "Заказ покупателя и срок изготовления", "doctype": "Sales Order", "mode": "new", "section": "quick"},
	{"label": "Приход материалов", "description": "Приёмка по заказу поставщику", "doctype": "Purchase Receipt", "mode": "new", "section": "quick", "operation": "receipt"},
	{"label": "Выдать в производство", "description": "Материалы на выбранное количество изделий", "doctype": "Stock Entry", "mode": "new", "section": "quick", "operation": "transfer"},
	{"label": "Выпуск изделия", "description": "Подготовить выпуск из производственного задания", "doctype": "Stock Entry", "mode": "new", "section": "quick", "operation": "manufacture"},
	{"label": "Отгрузить заказ", "description": "Подготовить отгрузку по заказу покупателя", "doctype": "Delivery Note", "mode": "new", "section": "quick", "operation": "delivery"},
	{"label": "Заказы", "description": "Покупатели, сроки и исполнение заказов", "doctype": "Sales Order", "mode": "list"},
	{"label": "Производство", "description": "Задания, материалы и выпуск", "doctype": "Work Order", "mode": "list"},
	{"label": "Склад", "description": "Выдача, возврат остатков и перемещение", "doctype": "Stock Entry", "mode": "list"},
	{"label": "Закупки", "description": "Заказы поставщикам и сроки поступления", "doctype": "Purchase Order", "mode": "list"},
	{"label": "Продажи и отгрузки", "description": "Передача готовых изделий покупателям", "doctype": "Delivery Note", "mode": "list"},
	{"label": "Материалы и изделия", "description": "Номенклатура и варианты", "doctype": "Item", "mode": "list"},
	{"label": "Состав и нормы", "description": "Спецификации материалов и операций", "doctype": "BOM", "mode": "list"},
	{"label": "Номерные изделия", "description": "Серийные номера и история", "doctype": "Serial No", "mode": "list"},
	{"label": "Деньги", "description": "Поступления и платежи", "doctype": "Payment Entry", "mode": "list"},
	{"label": "Качество", "description": "Проверка материалов и готовых изделий", "doctype": "Quality Inspection", "mode": "list"},
	{"label": "Счета покупателям", "description": "Выставленные счета и расчёты", "doctype": "Sales Invoice", "mode": "list"},
	{"label": "Счета поставщиков", "description": "Закупочные документы и задолженность", "doctype": "Purchase Invoice", "mode": "list"},
)


def validate_colour(value):
	value = value or "#21372F"
	if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
		raise ValueError("Цвет задаётся в формате #21372F.")
	return value


def normalise_actions(raw):
	if raw is None or raw == "":
		return deepcopy(list(DEFAULT_ACTIONS))
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except json.JSONDecodeError as exc:
			raise ValueError("Меню содержит некорректный JSON.") from exc
	if not isinstance(raw, list) or len(raw) > 30:
		raise ValueError("Меню должно быть массивом из не более 30 действий.")
	result = []
	for row in raw:
		if not isinstance(row, dict) or set(row) - {"label", "description", "doctype", "mode", "section", "defaults", "operation"}:
			raise ValueError("Действие допускает только label, description, doctype, mode, section, defaults и operation.")
		label = row.get("label")
		doctype = row.get("doctype")
		description = row.get("description", "")
		mode = row.get("mode", "list")
		if not isinstance(label, str) or not label.strip() or len(label) > 80:
			raise ValueError("У действия должно быть название длиной до 80 символов.")
		if not isinstance(description, str) or len(description) > 250:
			raise ValueError("Описание действия — строка длиной до 250 символов.")
		if not isinstance(doctype, str) or not re.fullmatch(r"[\w ()&./-]{1,100}", doctype):
			raise ValueError("Укажите существующий тип документа, а не ссылку или скрипт.")
		if mode not in ("list", "new"):
			raise ValueError("Допустимые режимы действия: list и new.")
		action = {"label": label.strip(), "description": description, "doctype": doctype, "mode": mode}
		if "operation" in row:
			operation = row["operation"]
			if (
				not isinstance(operation, str)
				or operation not in OPERATIONS
				or OPERATIONS[operation]["target"] != doctype
				or mode != "new"
				or "defaults" in row
			):
				raise ValueError("Операция должна соответствовать типу нового документа и не может сочетаться с defaults.")
			action["operation"] = operation
		if "section" in row:
			if row["section"] not in ("quick", "modules"):
				raise ValueError("Раздел действия: quick или modules.")
			action["section"] = row["section"]
		if "defaults" in row:
			defaults = row["defaults"]
			if (
				doctype != "Stock Entry"
				or mode != "new"
				or not isinstance(defaults, dict)
				or set(defaults) != {"stock_entry_type"}
				or not isinstance(defaults["stock_entry_type"], str)
				or defaults["stock_entry_type"] not in STOCK_ENTRY_PRESETS
			):
				raise ValueError("Предзаполнение допускает только тип нового складского документа: Material Issue, Material Receipt или Material Transfer.")
			action["defaults"] = dict(defaults)
		result.append(action)
	return result


EDITOR_OPERATIONS = {
	"Приёмка": "receipt", "Выдача в производство": "transfer",
	"Выпуск": "manufacture", "Отгрузка": "delivery",
}


def table_actions(rows):
	if not isinstance(rows, (list, tuple)) or len(rows) > 30:
		raise ValueError("В таблице меню допускается не более 30 строк.")
	result = []
	for row in rows:
		if not isinstance(row, dict):
			raise ValueError("Некорректная строка меню.")
		if row.get("open_mode", "Список") not in ("Список", "Новый документ"):
			raise ValueError("Выберите способ открытия: Список или Новый документ.")
		if row.get("menu_section", "Разделы") not in ("Разделы", "Быстрые действия"):
			raise ValueError("Выберите раздел меню.")
		action = {
			"label": row.get("label"), "description": row.get("description") or "",
			"doctype": row.get("action_doctype"),
			"mode": "new" if row.get("open_mode") == "Новый документ" else "list",
			"section": "quick" if row.get("menu_section") == "Быстрые действия" else "modules",
		}
		operation = row.get("guided_operation")
		if operation:
			if not isinstance(operation, str) or operation not in EDITOR_OPERATIONS:
				raise ValueError("Выберите существующую короткую операцию.")
			action["operation"] = EDITOR_OPERATIONS[operation]
		if row.get("stock_preset"):
			action["defaults"] = {"stock_entry_type": row["stock_preset"]}
		# Validate hidden rows too; turning visibility on must not reveal bad config.
		action = normalise_actions([action])[0]
		enabled = row.get("enabled", 1)
		if enabled not in (0, 1, "0", "1"):
			raise ValueError("Видимость кнопки задаётся флажком.")
		if enabled in (1, "1"):
			result.append(action)
	return result


def resolve_actions(raw, source=None, rows=None):
	if source in (None, "", "JSON"):
		return normalise_actions(raw)
	if source == "Таблица":
		return table_actions(rows or [])
	raise ValueError("Источник меню: JSON или Таблица.")


def actions_to_rows(actions):
	names = {value: key for key, value in EDITOR_OPERATIONS.items()}
	return [{
		"enabled": 1, "label": action["label"], "description": action["description"],
		"action_doctype": action["doctype"],
		"open_mode": "Новый документ" if action["mode"] == "new" else "Список",
		"menu_section": "Быстрые действия" if action.get("section") == "quick" else "Разделы",
		"guided_operation": names.get(action.get("operation"), ""),
		"stock_preset": action.get("defaults", {}).get("stock_entry_type", ""),
	} for action in normalise_actions(actions)]


def configured_actions(settings):
	rows = [row.as_dict() if hasattr(row, "as_dict") else row for row in (getattr(settings, "menu_items", None) or [])]
	return resolve_actions(getattr(settings, "actions_json", None), getattr(settings, "menu_source", None), rows)


def editor_rows(settings):
	rows = [row.as_dict() if hasattr(row, "as_dict") else row for row in (getattr(settings, "menu_items", None) or [])]
	if getattr(settings, "menu_source", None) != "Таблица":
		return actions_to_rows(configured_actions(settings))
	table_actions(rows)
	result = []
	for row in rows:
		item = actions_to_rows(table_actions([{**row, "enabled": 1}]))[0]
		item["enabled"] = 1 if row.get("enabled", 1) in (1, "1") else 0
		result.append(item)
	return result
