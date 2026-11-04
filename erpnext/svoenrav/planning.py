# License: GNU General Public License v3. See license.txt
import frappe
from frappe.utils import now

from erpnext.svoenrav.materials import get_material_coverage, readable
from erpnext.svoenrav.planning_rules import allocate
from erpnext.svoenrav.production import get_production_queue
from erpnext.svoenrav.portal import require_staff


@frappe.whitelist()
def get_queue_plan():
	require_staff()
	queue = get_production_queue(0)
	# Bound work and refuse a partial queue instead of overstating availability.
	if queue["total"] > 50 or queue["has_more"]:
		frappe.throw("План поддерживает до 50 доступных открытых заданий. Уменьшите очередь; неполный расчёт не выполняется.", frappe.ValidationError)
	orders = []
	for row in queue["rows"]:
		paused = bool(row.get("planning_paused") or row.get("native_stopped"))
		entry = {"work_order": row["name"], "paused": paused}
		if not paused:
			try:
				order = readable("Work Order", row["name"])
				entry.update(company=order.get("company"), report=get_material_coverage(row["name"]))
			except (frappe.PermissionError, frappe.ValidationError):
				entry["report"] = None
		orders.append(entry)
	return {**allocate(orders), "checked_at": now(), "scope": "Только доступные вам задания. Чужие резервы исключены из свободного остатка; незарезервированный спрос недоступных заданий не учитывается. Это последовательные чтения, а не блокировка склада. Расчёт ничего не резервирует."}
