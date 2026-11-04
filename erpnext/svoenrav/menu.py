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
