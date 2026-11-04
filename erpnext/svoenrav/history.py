# License: GNU General Public License v3. See license.txt
"""Read existing native Version status changes, never fabricate missing events."""
import json
import frappe
from erpnext.svoenrav.flow import visible_dict
from frappe.utils import get_url_to_form
from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.workshop import _source, get_order_card

FIELDS = {"status", "docstatus", "per_delivered", "per_billed", "produced_qty"}


def visible_changes(payload, visible_fields):
	try:
		data = json.loads(payload or "{}")
	except (ValueError, TypeError):
		return []
	if not isinstance(data, dict) or not isinstance(data.get("changed", []), list):
		return []
	return [{"field": row[0], "before": row[1], "after": row[2]} for row in data.get("changed", []) if isinstance(row, list) and len(row) == 3 and isinstance(row[0], str) and row[0] in FIELDS and row[0] in visible_fields and all(value is None or isinstance(value, (str, int, float, bool)) for value in row[1:])]


@frappe.whitelist()
def get_order_history(sales_order):
	require_staff()
	_source("Sales Order", sales_order)  # Check the requested order before Version queries.
	version_access = bool(frappe.has_permission("Version", ptype="read"))
	audit_access = bool(frappe.has_permission("SVOENRAV Operation Event", ptype="read"))
	if not version_access and not audit_access:
		return {"allowed": False, "rows": [], "partial": True, "notice": "Нет права чтения истории Version. Последние состояния смотрите в карточке; история не восстанавливается предположениями."}
	card = get_order_card(sales_order)
	refs = [("Sales Order", card["order"]["name"])]
	partial = False
	for key, doctype in (("production", "Work Order"), ("stock", "Stock Entry"), ("deliveries", "Delivery Note"), ("invoices", "Sales Invoice"), ("payments", "Payment Entry")):
		section = card[key]
		partial |= bool(section.get("has_more") or not section.get("allowed"))
		if section.get("allowed"):
			refs.extend((doctype, row["name"]) for row in section["rows"])
	if frappe.has_permission("SVOENRAV Payment Allocation", ptype="read"):
		table = frappe.qb.DocType("SVOENRAV Payment Allocation")
		allocations = frappe.qb.from_(table).select(table.name).where(table.sales_order == card["order"]["name"]).limit(51).run(as_dict=True)
		partial |= len(allocations) > 50
		refs.extend(("SVOENRAV Payment Allocation", row["name"]) for row in allocations[:50])
	refs = list(dict.fromkeys(refs))
	partial |= len(refs) > 50
	events = []
	for doctype, name in refs[:50]:
		try:
			doc = _source(doctype, name)
		except frappe.PermissionError:
			partial = True
			continue
		versions = frappe.get_list("Version", filters={"ref_doctype": doctype, "docname": name}, fields=["creation", "data"], order_by="creation desc, name desc", limit_page_length=21) if version_access else []
		if audit_access:
			audit_rows = audit_events(doctype, name, visible_dict(doc))
			partial |= audit_rows["partial"]
			events.extend(audit_rows["rows"])
		partial |= len(versions) > 20
		for version in versions[:20]:
			for change in visible_changes(version.get("data"), visible_dict(doc)):
				events.append({**change, "at": version.get("creation"), "doctype": doctype, "name": name, "url": get_url_to_form(doctype, name)})
	return {"allowed": True, "rows": sorted(events, key=lambda r: (str(r["at"] or ""), r["doctype"], r["name"], r["field"]), reverse=True), "partial": bool(partial), "notice": "Серверный журнал SVOENRAV и доступные записи Version. До 50 документов, 50 записей журнала и 20 версий каждого. Журнал действует после установки обновления; события без обработчиков (например прямой SQL) не восстанавливаются."}


def audit_events(doctype, name, visible_fields):
	from erpnext.svoenrav.events import FIELDS, VIRTUAL, visible_audit_fields
	allowed = set(FIELDS) | {row[1] for rows in VIRTUAL.values() for row in rows}
	visible_fields = visible_audit_fields(doctype, visible_fields)
	table = frappe.qb.DocType('SVOENRAV Operation Event')
	rows = frappe.qb.from_(table).select(table.creation,table.payload,table.before_payload,table.action).where((table.reference_doctype == doctype) & (table.reference_name == name)).orderby(table.creation, order=frappe.qb.desc).orderby(table.name, order=frappe.qb.desc).limit(51).run(as_dict=True)
	result = []
	for row in rows[:50]:
		before, after = json.loads(row['before_payload'] or '{}'), json.loads(row['payload'] or '{}')
		for field in sorted(set(before) | set(after)):
			if field in allowed and field in visible_fields and before.get(field) != after.get(field):
				result.append({'at':row['creation'],'doctype':doctype,'name':name,'url':get_url_to_form(doctype,name),'field':field,'before':before.get(field),'after':after.get(field),'source':'SVOENRAV','action':row['action']})
	return {'rows':result,'partial':len(rows)>50}
