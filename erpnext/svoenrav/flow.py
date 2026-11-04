# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt
"""Small, framework-independent rules for guided operations, not a stock ledger."""

from decimal import Decimal, InvalidOperation
from math import isfinite

OPERATIONS = {
	"receipt": {"label": "Приход материалов", "source": "Purchase Order", "target": "Purchase Receipt"},
	"transfer": {"label": "Выдать в производство", "source": "Work Order", "target": "Stock Entry", "purpose": "Material Transfer for Manufacture"},
	"manufacture": {"label": "Выпуск изделия", "source": "Work Order", "target": "Stock Entry", "purpose": "Manufacture"},
	"delivery": {"label": "Отгрузить заказ", "source": "Sales Order", "target": "Delivery Note"},
}


def decimal_qty(value):
	if isinstance(value, bool) or value is None:
		raise ValueError("Укажите числовое количество.")
	try:
		number = Decimal(str(value))
	except (InvalidOperation, ValueError):
		raise ValueError("Укажите числовое количество.") from None
	if not number.is_finite():
		raise ValueError("Количество должно быть конечным числом.")
	return number


def validate_source(source):
	if not isinstance(source, str) or not source.strip() or len(source) > 140 or "\x00" in source:
		raise ValueError("Выберите исходный документ.")
	return source.strip()


def validate_production(operation, order, quantity, *, separate_consumption=False):
	"""Keep the short path to one consumption scheme; advanced flows stay native."""
	if operation not in ("transfer", "manufacture"):
		raise ValueError("Неизвестная производственная операция.")
	if order.get("docstatus") != 1 or order.get("status") in ("Stopped", "Closed", "Completed", "Cancelled"):
		raise ValueError("Требуется действующее проведённое производственное задание.")
	if order.get("track_semi_finished_goods") or order.get("transfer_material_against") == "Job Card":
		raise ValueError("Для полуфабрикатов и операций по Job Card используйте полную форму задания.")
	if decimal_qty(order.get("process_loss_qty") or 0) or any(
		decimal_qty(row.get("process_loss_qty") or 0) for row in (order.get("operations") or [])
	):
		raise ValueError("В задании есть технологические потери. Оформите операцию из полной формы задания.")
	if order.get("subcontracting_inward_order") or order.get("disassembled_qty"):
		raise ValueError("Для давальческого производства или разборки используйте полную форму задания.")
	if separate_consumption:
		raise ValueError("Включено отдельное потребление материалов. Используйте полную форму задания, чтобы учесть ранее списанный расход.")
	planned = decimal_qty(order.get("qty") or 0)
	produced = decimal_qty(order.get("produced_qty") or 0)
	transferred = decimal_qty(order.get("material_transferred_for_manufacturing") or 0)
	if operation == "transfer":
		if order.get("skip_transfer"):
			raise ValueError("Задание настроено без отдельной передачи материалов. Переходите к выпуску.")
		maximum = planned - transferred
	else:
		maximum = min(planned, planned if order.get("skip_transfer") else transferred) - produced
	qty = decimal_qty(quantity)
	if qty <= 0:
		raise ValueError("Количество должно быть больше нуля.")
	if not isfinite(float(qty)) or float(qty) == 0:
		raise ValueError("Количество вне допустимого числового диапазона.")
	if qty > maximum:
		raise ValueError(f"Доступно количество не более {max(maximum, Decimal(0))}. Проверьте передачу материалов и предыдущий выпуск.")
	return qty
