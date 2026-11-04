# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt
"""Permission-checked adapters around native ERPNext document factories.

No custom stock ledger, automatic submit, ignore_permissions or direct SQL.
Native factories may prepare serial/batch bundles as in the standard UI.
"""

import frappe
from frappe.utils import get_url_to_form

from erpnext.svoenrav.flow import OPERATIONS, validate_production, validate_source, visible_dict
from erpnext.svoenrav.portal import require_staff

PAGE_URL = "/desk/svoenrav-workshop"
LIMIT = 20


def _operation(operation):
	if not isinstance(operation, str) or operation not in OPERATIONS:
		frappe.throw("Неизвестная операция.", frappe.ValidationError)
	return OPERATIONS[operation]


def _source(doctype, name):
	try:
		name = validate_source(name)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	return doc


def _available(spec):
	return frappe.has_permission(spec["source"], ptype="read") and frappe.has_permission(spec["target"], ptype="create")


@frappe.whitelist()
def get_options():
	require_staff()
	return {
		"operations": [{"key": key, **spec} for key, spec in OPERATIONS.items() if _available(spec)],
		"simple_default": "SVOENRAV Operator" in frappe.get_roles() and not set(frappe.get_roles()).intersection({"SVOENRAV Owner", "SVOENRAV Planner", "SVOENRAV Finance", "System Manager"}),
		"can_reserve": all(frappe.has_permission("Stock Reservation Entry", ptype=p) for p in ("read", "create", "submit")) and bool(frappe.has_permission("Work Order", ptype="write")),
		"can_allocate_payments": bool(frappe.has_permission("SVOENRAV Payment Allocation", ptype="create")),
		"can_read_orders": bool(frappe.has_permission("Sales Order", ptype="read")),
		"can_read_work_orders": bool(frappe.has_permission("Work Order", ptype="read")),
		"can_cutting": bool(frappe.has_permission("Work Order", ptype="read") and frappe.has_permission("Item", ptype="read") and frappe.has_permission("SVOENRAV Cutting Draft", ptype="create")),
	}


def _drafts(spec, name):
	if spec["source"] == "Work Order":
		filters = {"work_order": name, "purpose": spec["purpose"], "docstatus": 0}
	else:
		child, field = ("Purchase Receipt Item", "purchase_order") if spec["source"] == "Purchase Order" else ("Delivery Note Item", "against_sales_order")
		filters = [[spec["target"], "docstatus", "=", 0], [child, field, "=", name]]
	return _related(spec["target"], filters, [])


@frappe.whitelist()
def get_operation_drafts(operation, source_name):
	require_staff()
	spec = _operation(operation)
	if not _available(spec):
		frappe.throw("Нет права на операцию.", frappe.PermissionError)
	source = _source(spec["source"], source_name)
	return _drafts(spec, source.name)


@frappe.whitelist(methods=["POST"])
def prepare_operation(operation, source_name, quantity=None):
	"""Return an unsaved native document for review in the standard form."""
	require_staff()
	spec = _operation(operation)
	if not _available(spec):
		frappe.throw("Недостаточно прав для этой операции.", frappe.PermissionError)
	source = _source(spec["source"], source_name)
	if source.docstatus != 1 or source.get("status") in ("Stopped", "Closed", "Completed", "Cancelled", "On Hold"):
		frappe.throw("Выберите действующий проведённый документ.", frappe.ValidationError)
	drafts = _drafts(spec, source.name)
	if not drafts["allowed"]:
		frappe.throw("Для короткой операции требуется право чтения существующих черновиков целевого документа.", frappe.PermissionError)
	if drafts["rows"] or drafts["has_more"]:
		return {"existing_drafts": drafts}
	if spec["source"] == "Work Order":
		# A previously used consumption scheme may remain after settings change.
		# Only test existence for this permission-checked source; do not expose
		# any names or contents of otherwise inaccessible stock documents.
		prior_consumption = frappe.db.exists("Stock Entry", {
			"work_order": source.name,
			"purpose": "Material Consumption for Manufacture",
			"docstatus": 1,
		})
		try:
			qty = validate_production(
				operation,
				visible_dict(source),
				quantity,
				separate_consumption=bool(prior_consumption or frappe.db.get_single_value("Manufacturing Settings", "material_consumption")),
			)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		_check_specification(source)
		from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

		target = frappe.get_doc(make_stock_entry(source.name, spec["purpose"], qty=float(qty)))
	else:
		if quantity is not None and quantity != "":
			frappe.throw("Количество строк приёмки и отгрузки уточняется в подготовленном документе.", frappe.ValidationError)
		if operation == "receipt":
			from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

			target = make_purchase_receipt(source.name)
		else:
			from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

			target = make_delivery_note(source.name)
	if target.doctype != spec["target"] or target.docstatus != 0 or not target.is_new():
		frappe.throw("Ожидался новый черновик документа.", frappe.ValidationError)
	target.check_permission("create")
	if not target.get("items"):
		frappe.throw("Нет доступных строк для операции. Возможно, документ уже исполнен.", frappe.ValidationError)
	return target.as_dict()


def _related(doctype, filters, fields):
	if not frappe.has_permission(doctype, ptype="read"):
		return {"doctype": doctype, "allowed": False, "rows": [], "has_more": False}
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=["name", "docstatus", "modified", *fields],
		order_by="modified desc, name asc",
		limit_page_length=LIMIT + 1,
		distinct=True,
	)
	return {
		"doctype": doctype,
		"allowed": True,
		"rows": [{**row, "url": get_url_to_form(doctype, row["name"])} for row in rows[:LIMIT]],
		"has_more": len(rows) > LIMIT,
	}


@frappe.whitelist()
def get_order_card(sales_order):
	require_staff()
	order = _source("Sales Order", sales_order)
	# Parent queries with child filters retain document permissions. Do not query
	# child tables directly or join by item_code, customer or free text.
	production = _related("Work Order", {"sales_order": order.name}, ["item_name", "qty", "produced_qty", "material_transferred_for_manufacturing", "skip_transfer", "status", "expected_delivery_date"])
	# Stock Entry has a Link to Work Order, but DatabaseQuery does not follow Link
	# joins automatically. Use a permission-aware subquery of accessible work orders.
	stock = {"doctype": "Stock Entry", "allowed": False, "rows": [], "has_more": False}
	if frappe.has_permission("Stock Entry", ptype="read") and frappe.has_permission("Work Order", ptype="read"):
		work_orders = frappe.get_list("Work Order", filters={"sales_order": order.name}, pluck="name", order_by="name asc", limit_page_length=501)
		if len(work_orders) > 500:
			stock = {"doctype": "Stock Entry", "allowed": True, "rows": [], "has_more": True, "note": "Более 500 производственных заданий. Используйте полный список документов."}
		elif work_orders:
			stock = _related("Stock Entry", {"work_order": ["in", work_orders]}, ["purpose", "work_order", "posting_date"])
		else:
			stock = {"doctype": "Stock Entry", "allowed": True, "rows": [], "has_more": False}
	invoices = _related("Sales Invoice", [["Sales Invoice Item", "sales_order", "=", order.name]], ["posting_date", "status", "currency", "grand_total", "outstanding_amount"])
	deliveries = _related("Delivery Note", [["Delivery Note Item", "against_sales_order", "=", order.name]], ["posting_date", "status"])
	return {
		"order": {field: order.get(field) for field in ("name", "customer_name", "status", "docstatus", "transaction_date", "delivery_date", "currency", "grand_total", "advance_paid", "per_delivered", "per_billed")},
		"url": get_url_to_form("Sales Order", order.name),
		"items": [{field: row.get(field) for field in ("item_code", "item_name", "qty", "uom", "delivered_qty", "delivery_date")} for row in order.get("items", [])],
		"production": production,
		"stock": stock,
		"deliveries": deliveries,
		"invoices": invoices,
		"payments": _payments_with_allocations(order.name, invoices),
		"timeline": _timeline(order, [production, stock, deliveries, invoices]),
	}


def _payments(order_name, invoices):
	# Payment references may point to SO directly or to a readable linked invoice.
	sections = [_related("Payment Entry", [["Payment Entry Reference", "reference_doctype", "=", "Sales Order"], ["Payment Entry Reference", "reference_name", "=", order_name]], ["posting_date", "payment_type", "paid_amount", "paid_from_account_currency", "received_amount", "paid_to_account_currency"])]
	for row in invoices["rows"]:
		sections.append(_related("Payment Entry", [["Payment Entry Reference", "reference_doctype", "=", "Sales Invoice"], ["Payment Entry Reference", "reference_name", "=", row["name"]]], ["posting_date", "payment_type", "paid_amount", "paid_from_account_currency", "received_amount", "paid_to_account_currency"]))
	rows = {r["name"]: r for section in sections for r in section["rows"]}
	return {"allowed": sections[0]["allowed"], "rows": sorted(rows.values(), key=lambda r: (str(r.get("modified") or ""), r["name"]), reverse=True)[:LIMIT], "has_more": invoices["has_more"] or len(rows) > LIMIT or any(s["has_more"] for s in sections), "note": "Показаны полные суммы платёжных документов, не доля оплаты этого заказа. Суммы разных валют не суммируются. Платежи по недоступным счетам и журнальные проводки могут отсутствовать."}


def _timeline(order, sections):
	# A document index, not a fabricated audit trail of every status transition.
	events = [{"at": order.get("modified"), "doctype": "Sales Order", "name": order.name, "docstatus": order.get("docstatus"), "url": get_url_to_form("Sales Order", order.name)}]
	for section in sections:
		for row in section["rows"]:
			events.append({"at": row.get("modified"), "doctype": section["doctype"], "name": row["name"], "docstatus": row.get("docstatus"), "url": row["url"]})
	return {"rows": sorted(events, key=lambda r: (str(r["at"] or ""), r["doctype"], r["name"]), reverse=True), "partial": any(not s["allowed"] or s["has_more"] for s in sections), "notice": "Последние изменения доступных связанных документов. Это не полный журнал смены статусов. Полная история каждого документа находится в его штатной форме."}


def _check_specification(order):
	"""A captured baseline cannot silently drift in the guided production path."""
	doctype = "SVOENRAV Specification Snapshot"
	if not frappe.db.exists(doctype, {"work_order": order.name}):
		return  # Legacy orders can be captured explicitly; never invent an old BOM.
	if not frappe.has_permission(doctype, ptype="read"):
		frappe.throw("Нет права проверить зафиксированный состав. Используйте полную форму задания.", frappe.PermissionError)
	name = frappe.db.get_value(doctype, {"work_order": order.name}, "name")
	rows = [{"name": name}] if name else []
	if not rows:
		frappe.throw("Снимок состава недоступен. Короткая операция остановлена.", frappe.PermissionError)
	snapshot = _source(doctype, rows[0]["name"])
	from erpnext.svoenrav.spec_rules import specification
	try:
		_, digest = specification(visible_dict(order))
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	if not snapshot.get("fingerprint") or snapshot.get("fingerprint") != digest:
		frappe.throw("Нормы задания отличаются от зафиксированного состава. Проверьте версию и оформите новое задание для изменения норм.", frappe.ValidationError)


def _payments_with_allocations(order_name, invoices):
	from erpnext.svoenrav.payments import enrich_payments
	return enrich_payments(_payments(order_name, invoices), order_name)
