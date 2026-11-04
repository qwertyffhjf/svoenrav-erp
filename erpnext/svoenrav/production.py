# License: GNU General Public License v3. See license.txt
import frappe
from frappe.utils import get_url_to_form, nowdate

from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.queue_rules import normalise_queue, sort_queue


@frappe.whitelist()
def get_production_queue(start=0):
	require_staff()
	if not frappe.has_permission("Work Order", ptype="read"):
		frappe.throw("Нет права чтения производственных заданий.", frappe.PermissionError)
	if isinstance(start, bool) or not str(start).isdigit() or not 0 <= int(start) <= 1000:
		frappe.throw("Некорректная страница очереди.", frappe.ValidationError)
	orders = frappe.get_list(
		"Work Order", filters={"docstatus": 1, "status": ["not in", ["Completed", "Closed", "Cancelled"]]},
		fields=["name", "item_name", "qty", "produced_qty", "stock_uom", "status", "expected_delivery_date", "creation"],
		order_by="creation asc, name asc", limit_page_length=1001,
	)
	if len(orders) > 1000:
		frappe.throw("Более 1000 доступных открытых заданий. Используйте полный список ERPNext; неполная очередь не показывается.", frappe.ValidationError)
	settings = frappe.get_single("SVOENRAV Production Settings")
	try:
		planning = normalise_queue([row.as_dict() for row in (settings.get("queue_items") or [])])
	except ValueError:
		frappe.throw("Проверьте настройки очереди SVOENRAV.", frappe.ValidationError)
	rows = sort_queue(orders, planning, nowdate())
	offset = int(start)
	return {
		"rows": [{**row, "url": get_url_to_form("Work Order", row["name"])} for row in rows[offset:offset + 50]],
		"start": offset, "has_more": len(rows) > offset + 50, "total": len(rows),
		"can_configure": bool(frappe.has_permission("SVOENRAV Production Settings", ptype="write")),
		"settings_url": get_url_to_form("SVOENRAV Production Settings"),
	}
