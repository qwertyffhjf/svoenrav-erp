# License: GNU General Public License v3. See license.txt
"""Explicit, atomic native SRE creation from a freshly checked queue plan."""
import frappe
from frappe.utils import get_url_to_form
from erpnext.svoenrav.material_rules import quantity, ZERO
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.planning import get_queue_plan
from erpnext.svoenrav.production import get_production_queue
from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.transactions import lock


@frappe.whitelist(methods=["POST"])
def reserve_queue():
	require_staff()
	for permission in ("create", "submit", "read"):
		if not frappe.has_permission("Stock Reservation Entry", ptype=permission):
			frappe.throw("Нужны права чтения, создания и проведения складских резервов.", frappe.PermissionError)
	queue = get_production_queue(0)
	if queue["has_more"] or queue["total"] > 50:
		frappe.throw("Для резервирования требуется полная очередь до 50 заданий.", frappe.ValidationError)
	orders, keys = {}, set()
	for name in sorted(row["name"] for row in queue["rows"] if not row.get("planning_paused") and not row.get("native_stopped")):
		lock("Work Order", name)
		order = readable("Work Order", name)
		order.check_permission("write")
		orders[name] = order
		for row in order.get("required_items") or []:
			keys.add((row.item_code, row.get("source_warehouse") or order.get("source_warehouse")))
	for item, warehouse in sorted(keys, key=lambda key: (key[0], key[1] or "")):
		if warehouse:
			frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "name", for_update=True)
	plan = get_queue_plan()
	if not plan["complete"]:
		frappe.throw("Неполные данные: резервы не созданы.", frappe.ValidationError)
	if {r["work_order"] for r in plan["orders"] if r["status"] != "paused"} != set(orders):
		frappe.throw("Очередь изменилась. Повторите проверку.", frappe.ValidationError)
	created = []
	for entry in plan["orders"]:
		if entry["status"] == "paused":
			continue
		order = orders[entry["work_order"]]
		if order.get("docstatus") != 1 or order.get("status") in ("Completed", "Closed", "Cancelled", "Stopped"):
			frappe.throw("Состояние задания изменилось. Повторите расчёт.", frappe.ValidationError)
		for group in entry["rows"]:
			remaining = quantity(group["planned_free"])
			for row in order.get("required_items") or []:
				if row.item_code != group["item_code"] or (row.get("source_warehouse") or order.get("source_warehouse")) != group["warehouse"]:
					continue
				need = max(quantity(row.required_qty) - quantity(row.consumed_qty if order.get("skip_transfer") else row.transferred_qty) - quantity(row.stock_reserved_qty), ZERO)
				qty = min(remaining, need)
				if qty <= ZERO:
					continue
				doc = frappe.new_doc("Stock Reservation Entry")
				doc.update({"item_code": row.item_code, "warehouse": group["warehouse"], "stock_uom": group["stock_uom"], "company": order.company, "voucher_type": "Work Order", "voucher_no": order.name, "voucher_detail_no": row.name, "voucher_qty": row.required_qty, "available_qty": float(qty), "reserved_qty": float(qty), "reservation_based_on": "Qty"})
				doc.insert()
				doc.submit()  # Native validations, no ignore_permissions, no custom ledger.
				created.append({"name": doc.name, "url": get_url_to_form(doc.doctype, doc.name)})
				remaining -= qty
			if remaining > ZERO:
				frappe.throw("Не удалось сопоставить план строкам задания. Вся операция отменена.", frappe.ValidationError)
	return {"created": created, "count": len(created), "notice": "Созданы и проведены штатные складские резервы. Это не списание материала."}
