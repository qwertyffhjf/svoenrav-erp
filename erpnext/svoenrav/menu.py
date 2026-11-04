# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt
"""Menu definitions are data, never executable code or arbitrary URLs."""

import json
import re

DEFAULT_ACTIONS = (
	{"label": "Принять материал", "description": "Кожа, фурнитура и другие поступления", "doctype": "Purchase Receipt", "mode": "new"},
	{"label": "Производство", "description": "Задания, материалы и выпуск", "doctype": "Work Order", "mode": "list"},
	{"label": "Складские операции", "description": "Выдача, возврат остатков, перемещение", "doctype": "Stock Entry", "mode": "list"},
	{"label": "Продажи", "description": "Заказы покупателей и сроки", "doctype": "Sales Order", "mode": "list"},
	{"label": "Материалы и изделия", "description": "Номенклатура и варианты", "doctype": "Item", "mode": "list"},
	{"label": "Состав и нормы", "description": "Спецификации материалов и операций", "doctype": "BOM", "mode": "list"},
	{"label": "Номерные изделия", "description": "Серийные номера и история", "doctype": "Serial No", "mode": "list"},
	{"label": "Деньги", "description": "Поступления и платежи", "doctype": "Payment Entry", "mode": "list"},
	{"label": "Качество", "description": "Проверка материалов и готовых изделий", "doctype": "Quality Inspection", "mode": "list"},
)


def validate_colour(value):
	value = value or "#21372F"
	if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
		raise ValueError("Цвет задаётся в формате #21372F.")
	return value


def normalise_actions(raw):
	if raw is None or raw == "":
		return [dict(action) for action in DEFAULT_ACTIONS]
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except json.JSONDecodeError as exc:
			raise ValueError("Меню содержит некорректный JSON.") from exc
	if not isinstance(raw, list) or len(raw) > 30:
		raise ValueError("Меню должно быть массивом из не более 30 действий.")
	result = []
	for row in raw:
		if not isinstance(row, dict) or set(row) - {"label", "description", "doctype", "mode"}:
			raise ValueError("Действие допускает только label, description, doctype и mode.")
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
		result.append({"label": label.strip(), "description": description, "doctype": doctype, "mode": mode})
	return result
