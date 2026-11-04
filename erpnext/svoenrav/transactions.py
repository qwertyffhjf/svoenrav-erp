# License: GNU General Public License v3. See license.txt
"""Transaction-scoped locks and guards. Never commits the caller's transaction."""
import frappe

PURPOSES = {"Material Transfer for Manufacture", "Manufacture"}


def lock(doctype, name):
	if not frappe.db.get_value(doctype, name, "name", for_update=True):
		frappe.throw("Исходный документ больше не существует.", frappe.ValidationError)


def draft_sources(doc):
	if doc.get("is_return") or doc.get("docstatus") == 2:
		return []
	if doc.doctype == "Stock Entry":
		return [("Work Order", doc.work_order)] if doc.get("work_order") and doc.get("purpose") in PURPOSES else []
	field = {"Purchase Receipt": ("Purchase Order", "purchase_order"), "Delivery Note": ("Sales Order", "against_sales_order")}.get(doc.doctype)
	return sorted({(field[0], row.get(field[1])) for row in doc.get("items", []) if row.get(field[1])}) if field else []


def guard_duplicate_draft(doc, method=None):
	"""One pending operation per source. Includes otherwise unreadable drafts.

	Lock the parent, then use a locking/current read, not a permission-filtered
	list or an old REPEATABLE READ snapshot. Names of hidden drafts never escape.
	"""
	sources = draft_sources(doc)
	for doctype, name in sources:
		lock(doctype, name)
	for doctype, name in sources:
		target = frappe.qb.DocType(doc.doctype)
		query = frappe.qb.from_(target).select(target.name).where((target.docstatus == 0) & (target.name != (doc.get("name") or "")))
		if doc.doctype == "Stock Entry":
			query = query.where((target.work_order == name) & (target.purpose == doc.purpose))
		else:
			child = frappe.qb.DocType(doc.doctype + " Item")
			field = "purchase_order" if doc.doctype == "Purchase Receipt" else "against_sales_order"
			query = query.join(child).on(child.parent == target.name).where(child[field] == name)
		if query.limit(1).for_update().run():
			frappe.throw("Для этого источника и операции уже существует другой черновик. Обработайте его перед созданием нового. Если он недоступен, обратитесь к ответственному.", frappe.ValidationError)


def lock_reservation(doc, method=None):
	if doc.get("voucher_type") == "Work Order" and doc.get("voucher_no"):
		lock("Work Order", doc.voucher_no)
	if doc.get("item_code") and doc.get("warehouse"):
		frappe.db.get_value("Bin", {"item_code": doc.item_code, "warehouse": doc.warehouse}, "name", for_update=True)
