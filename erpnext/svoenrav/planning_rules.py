# License: GNU General Public License v3. See license.txt
"""Advisory allocation in queue order, never creates stock reservations."""
from decimal import Decimal, InvalidOperation


def number(value):
	if value is None or isinstance(value, bool):
		raise ValueError("Недоступно количество.")
	try:
		result = Decimal(str(value))
	except InvalidOperation:
		raise ValueError("Некорректное количество.") from None
	if not result.is_finite() or result < 0:
		raise ValueError("Некорректное количество.")
	return result


def allocate(orders):
	"""Input must contain the complete readable queue, sorted by priority.

	Unknown active demand blocks the entire simulation; paused demand is skipped.
	Repeated stock observations use the minimum free quantity. Own reserves are
	never pooled or released to other orders. This is not a transactional snapshot.
	"""
	pools, reserved, units = {}, {}, {}
	incomplete = False
	for order in orders:
		if order.get("paused"):
			continue
		report = order.get("report") or {}
		if report.get("review_required") or report.get("status") == "review" or not report.get("rows"):
			incomplete = True
		for row in report.get("rows", []):
			try:
				key = (order["company"], row["item_code"], row["warehouse"])
				if not all(key) or not row.get("stock_uom") or row.get("status") in ("unknown", "review"):
					raise ValueError("Неполные данные")
				free, own = number(row.get("free")), number(row.get("own_reserved"))
				number(row.get("pending"))
				actual, total = number(row.get("actual")), number(row.get("reserved_total"))
				if own > total or total > actual or free > actual - total:
					raise ValueError("Несогласованный остаток")
				if key in units and units[key] != row["stock_uom"]:
					raise ValueError("Разные единицы")
				units[key] = row["stock_uom"]
				pools[key] = min(pools.get(key, free), free)
				reserved[key] = reserved.get(key, Decimal(0)) + own
			except (KeyError, ValueError, TypeError):
				incomplete = True
	# Reject overlapping own reserves, even if each row individually looked valid.
	for order in orders:
		if order.get("paused"):
			continue
		for row in (order.get("report") or {}).get("rows", []):
			key = (order.get("company"), row.get("item_code"), row.get("warehouse"))
			try:
				if reserved.get(key, 0) > number(row.get("reserved_total")):
					incomplete = True
			except ValueError:
				incomplete = True
	result = []
	for order in orders:
		rows = []
		paused = order.get("paused", False)
		for source in (order.get("report") or {}).get("rows", []):
			row = {k: source.get(k) for k in ("item_code", "item_name", "warehouse", "stock_uom", "pending", "own_reserved")}
			row.update(planned_free=None, shortage=None)
			if not paused and not incomplete:
				key = (order["company"], row["item_code"], row["warehouse"])
				need = max(number(row["pending"]) - number(row["own_reserved"]), Decimal(0))
				assigned = min(need, pools[key])
				pools[key] -= assigned
				row.update(planned_free=float(assigned), shortage=float(need - assigned))
			rows.append(row)
		status = "paused" if paused else "unknown" if incomplete else "shortage" if any(row["shortage"] > 0 for row in rows) else "covered"
		result.append({"work_order": order["work_order"], "status": status, "rows": rows})
	return {"complete": not incomplete, "orders": result}
