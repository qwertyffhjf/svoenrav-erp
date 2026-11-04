# License: GNU General Public License v3. See license.txt
"""Material availability for one readable Work Order; never creates reserves."""
import frappe
from frappe.utils import get_url_to_form, now

from erpnext.svoenrav.flow import validate_source, visible_dict
from erpnext.svoenrav.material_rules import EPSILON, ZERO, coverage, group_requirements, quantity
from erpnext.svoenrav.portal import require_staff


def readable(doctype, name):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	return doc


def own_reservations(order, groups):
	"""Voucher row totals can span warehouses. Verify visible SREs per detail,
	then return only quantities reserved at the specific source warehouse."""
	if not any(group["own_reserved"] for group in groups):
		return {}, True
	if not frappe.has_permission("Stock Reservation Entry", ptype="read"):
		return {}, False
	rows = frappe.get_list("Stock Reservation Entry", filters={"voucher_type": "Work Order", "voucher_no": order.name, "docstatus": 1}, fields=["voucher_detail_no", "item_code", "warehouse", "reserved_qty", "delivered_qty", "transferred_qty", "consumed_qty"], limit_page_length=2001)
	if len(rows) > 2000:
		return {}, False
	by_detail = {row.name: row for row in order.get("required_items")}
	totals = {}
	by_warehouse = {}
	try:
		for row in rows:
			detail = row.get("voucher_detail_no")
			if detail not in by_detail or row.get("item_code") != by_detail[detail].get("item_code") or not row.get("warehouse"):
				return {}, False
			pending = quantity(row.get("reserved_qty")) - quantity(row.get("delivered_qty")) - quantity(row.get("transferred_qty")) - quantity(row.get("consumed_qty"))
			if pending < -EPSILON:
				return {}, False
			pending = max(pending, ZERO)
			totals[detail] = totals.get(detail, ZERO) + pending
			key = (row["item_code"], row["warehouse"])
			by_warehouse[key] = by_warehouse.get(key, ZERO) + pending
		for name, row in by_detail.items():
			if abs(totals.get(name, ZERO) - quantity(row.get("stock_reserved_qty"))) > EPSILON:
				return {}, False
	except ValueError:
		return {}, False
	return by_warehouse, True


@frappe.whitelist()
def get_material_coverage(work_order):
	require_staff()
	try:
		name = validate_source(work_order)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	order = readable("Work Order", name)
	if order.get("docstatus") != 1 or order.get("status") in ("Completed", "Closed", "Cancelled"):
		frappe.throw("Выберите открытое проведённое производственное задание.", frappe.ValidationError)
	if order.get("skip_transfer") not in (0, 1) or not order.get("company"):
		frappe.throw("Недостаточно доступных данных задания для проверки материалов.", frappe.PermissionError)
	try:
		groups = group_requirements([visible_dict(row) for row in (order.get("required_items") or [])], order.get("source_warehouse"), skip_transfer=bool(order.get("skip_transfer")))
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	balances = {}
	reservation_map, reservations_known = own_reservations(order, groups)
	items = {}
	warehouses = {}
	for group in groups:
		item_code, warehouse = group["item_code"], group["warehouse"]
		key = (item_code, warehouse)
		balances[key] = {"known": False}
		if not warehouse or not frappe.has_permission("Bin", ptype="read"):
			continue
		try:
			if item_code not in items:
				items[item_code] = readable("Item", item_code)
			if warehouse not in warehouses:
				warehouses[warehouse] = readable("Warehouse", warehouse)
		except frappe.PermissionError:
			# Do not expose restricted warehouse names, quantities or item labels.
			group["warehouse"] = None
			group["item_name"] = item_code
			continue
		item, wh = items[item_code], warehouses[warehouse]
		if wh.get("company") != order.get("company") or wh.get("is_group") != 0 or item.get("is_stock_item") != 1:
			balances[key] = {"known": False, "review": "Проверьте склад, компанию и признак складского учёта материала."}
			continue
		filters = {"item_code": item_code, "warehouse": warehouse}
		rows = frappe.get_list("Bin", filters=filters, fields=["actual_qty", "reserved_stock", "stock_uom"], limit_page_length=1)
		if rows:
			balance = rows[0]
			balances[key] = {**balance, "known": all(balance.get(field) is not None for field in ("actual_qty", "reserved_stock", "stock_uom"))}
		elif not frappe.db.exists("Bin", filters):
			# Absence of a Bin is zero stock; an existing but unreadable Bin is unknown.
			balances[key] = {"known": True, "actual_qty": 0, "reserved_stock": 0, "stock_uom": item.get("stock_uom")}
		balances[key].update(own_reserved=reservation_map.get(key, ZERO), reservations_known=reservations_known)
		if any(doc.get(field) not in (0,) for doc, field in ((wh, "disabled"), (item, "disabled"), (item, "has_serial_no"), (item, "has_batch_no"))):
			balances[key]["review"] = "Проверьте доступность склада/материала, партии и серийные номера в полной форме."
	review = bool(order.get("track_semi_finished_goods") or order.get("transfer_material_against") == "Job Card" or order.get("subcontracting_inward_order") or order.get("from_wip_warehouse") or order.get("process_loss_qty") or order.get("disassembled_qty") or order.get("status") == "Stopped" or frappe.db.get_single_value("Manufacturing Settings", "material_consumption"))
	try:
		result = coverage(groups, balances, force_review=review)
	except ValueError:
		frappe.throw("Остатки или резервы недоступны для расчёта. Проверьте права и исходные данные.", frappe.ValidationError)
	return {
		**result, "work_order": order.name, "url": get_url_to_form("Work Order", order.name),
		"checked_at": now(), "review_required": review,
		"notice": "Проверка на текущий момент. Незарезервированный остаток доступен и другим заданиям. Проверка не создаёт резерв и не подтверждает готовность к выпуску.",
	}
