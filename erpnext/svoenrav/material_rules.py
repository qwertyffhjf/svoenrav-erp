# License: GNU General Public License v3. See license.txt
"""Read-only material coverage. No allocation between orders or stock posting."""
from decimal import Decimal, InvalidOperation
from math import isfinite


ZERO = Decimal(0)
EPSILON = Decimal("0.000001")


def quantity(value, *, signed=False):
	if value is None or isinstance(value, bool):
		raise ValueError("Нет доступного числового значения материала.")
	try:
		result = Decimal(str(value))
	except (InvalidOperation, ValueError):
		raise ValueError("Некорректное количество материала.") from None
	if not result.is_finite() or not isfinite(float(result)) or (result != 0 and float(result) == 0) or (not signed and result < 0):
		raise ValueError("Некорректное количество материала.")
	return result


def group_requirements(rows, default_warehouse=None, *, skip_transfer=False):
	if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 200:
		raise ValueError("Для проверки требуется от 1 до 200 строк материалов.")
	groups = {}
	for row in rows:
		item = row.get("item_code")
		uom = row.get("stock_uom")
		warehouse = row.get("source_warehouse") or default_warehouse
		if not isinstance(item, str) or not item or not isinstance(uom, str) or not uom:
			raise ValueError("В строке материала недоступен артикул или складская единица.")
		key = (item, warehouse)
		if key in groups and groups[key]["stock_uom"] != uom:
			raise ValueError("У одного материала на одном складе указаны разные складские единицы.")
		group = groups.setdefault(key, {"item_code": item, "item_name": row.get("item_name") or item, "warehouse": warehouse, "stock_uom": uom, "required": ZERO, "transferred": ZERO, "consumed": ZERO, "returned": ZERO, "own_reserved": ZERO, "pending": ZERO})
		required = quantity(row.get("required_qty"))
		transferred = quantity(row.get("transferred_qty"))
		consumed = quantity(row.get("consumed_qty"))
		returned = quantity(row.get("returned_qty"))
		reserved = quantity(row.get("stock_reserved_qty"))
		group["required"] += required
		group["transferred"] += transferred
		group["consumed"] += consumed
		group["returned"] += returned
		group["own_reserved"] += reserved
		# Match native Work Order pending-to-issue logic. Round each row up to
		# zero separately: surplus on one operation must not conceal another.
		group["pending"] += max(required - (consumed if skip_transfer else transferred), ZERO)
	if len(groups) > 100:
		raise ValueError("Более 100 сочетаний материала и склада. Используйте полную форму задания.")
	return list(groups.values())


def coverage(groups, balances, *, force_review=False):
	result = []
	for group in groups:
		row = dict(group)
		balance = balances.get((group["item_code"], group["warehouse"]))
		row.update(actual=None, reserved_total=None, own_reserved=None, free=None, usable=None, shortage=None, status="unknown", note="Нет доступных данных склада.")
		if balance and balance.get("known"):
			actual = quantity(balance.get("actual_qty"), signed=True)
			reserved = quantity(balance.get("reserved_stock"))
			own = quantity(balance.get("own_reserved", group["own_reserved"]))
			row.update(actual=actual, reserved_total=reserved)
			row["own_reserved"] = own
			if not balance.get("reservations_known", True):
				row.update(own_reserved=None, free=max(actual - reserved, ZERO), note="Не удалось подтвердить резервы задания на этом складе.")
			elif own > reserved + EPSILON or reserved > actual + EPSILON:
				row["note"] = "Остаток и резервы требуют сверки. Обновите данные и проверьте склад."
			elif balance.get("stock_uom") != group["stock_uom"]:
				row["note"] = "Складские единицы материала не совпадают."
			else:
				free = max(actual - reserved, ZERO)
				usable = min(max(actual, ZERO), free + min(own, reserved))
				shortage = max(group["pending"] - usable, ZERO)
				status = "shortage" if shortage > ZERO else "reserved" if own >= group["pending"] else "unreserved"
				if group["pending"] == ZERO:
					status = "issued"
				row.update(free=free, usable=usable, shortage=shortage, status=status, note="")
		if row["returned"] > ZERO:
			row.update(status="review", note="Были возвраты материалов. Проверьте повторную потребность в полной форме задания.")
		if balance and balance.get("review"):
			row.update(status="review", note=balance["review"])
		result.append(row)
	statuses = {row["status"] for row in result}
	if force_review or statuses & {"unknown", "review"}:
		status = "review"
	elif "shortage" in statuses:
		status = "shortage"
	elif "unreserved" in statuses:
		status = "unreserved"
	elif statuses == {"issued"}:
		status = "issued"
	else:
		status = "reserved"
	# Decimal output is converted at the boundary; input data is never changed.
	return {"status": status, "rows": [{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()} for row in result]}
