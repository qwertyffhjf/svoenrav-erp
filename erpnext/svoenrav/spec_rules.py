# License: GNU General Public License v3. See license.txt
"""Stable specification fingerprint, independent of progress and BOM edits."""
import hashlib
import json
from decimal import Decimal, InvalidOperation


def amount(value):
	if value is None or isinstance(value, bool):
		raise ValueError("Недоступна норма или количество.")
	try:
		number = Decimal(str(value))
	except InvalidOperation:
		raise ValueError("Некорректная норма.") from None
	if not number.is_finite() or number < 0 or number > Decimal("1e12"):
		raise ValueError("Некорректная норма.")
	return format(number.normalize(), "f")


def specification(order):
	for field in ("production_item", "bom_no", "stock_uom", "company"):
		if not isinstance(order.get(field), str) or not order[field]:
			raise ValueError("Недостаточно данных состава задания: " + field)
	rows = order.get("required_items")
	if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 200:
		raise ValueError("Требуется от 1 до 200 строк состава.")
	items = []
	for row in rows:
		if not row.get("item_code") or not row.get("stock_uom"):
			raise ValueError("Недоступны материал или единица нормы.")
		items.append({"item_code": row["item_code"], "stock_uom": row["stock_uom"], "required_qty": amount(row.get("required_qty")), "operation": row.get("operation") or ""})
	data = {"schema": 1, **{key: order[key] for key in ("company", "production_item", "bom_no", "stock_uom")}, "qty": amount(order.get("qty")), "items": sorted(items, key=lambda r: (r["item_code"], r["stock_uom"], r["operation"], r["required_qty"]))}
	encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return encoded, hashlib.sha256(encoded.encode()).hexdigest()
