# License: GNU General Public License v3. See license.txt
"""Read existing native Version status changes, never fabricate missing events."""
import json
import frappe
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
	if not frappe.has_permission("Version", ptype="read"):
		return {"allowed": False, "rows": [], "partial": True, "notice": "Нет права чтения истории Version. Последние состояния смотрите в карточке; история не восстанавливается предположениями."}
	card = get_order_card(sales_order)
	refs = [("Sales Order", card["order"]["name"])]
	partial = False
	for key, doctype in (("production", "Work Order"), ("stock", "Stock Entry"), ("deliveries", "Delivery Note"), ("invoices", "Sales Invoice"), ("payments", "Payment Entry")):
		section = card[key]
		partial |= bool(section.get("has_more") or not section.get("allowed"))
		if section.get("allowed"):
			refs.extend((doctype, row["name"]) for row in section["rows"])
	refs = list(dict.fromkeys(refs))
	partial |= len(refs) > 50
	events = []
	for doctype, name in refs[:50]:
		try:
			doc = _source(doctype, name)
		except frappe.PermissionError:
			partial = True
			continue
		versions = frappe.get_list("Version", filters={"ref_doctype": doctype, "docname": name}, fields=["creation", "data"], order_by="creation desc, name desc", limit_page_length=21)
		partial |= len(versions) > 20
		for version in versions[:20]:
			for change in visible_changes(version.get("data"), doc.as_dict()):
				events.append({**change, "at": version.get("creation"), "doctype": doctype, "name": name, "url": get_url_to_form(doctype, name)})
	return {"allowed": True, "rows": sorted(events, key=lambda r: (str(r["at"] or ""), r["doctype"], r["name"], r["field"]), reverse=True), "partial": bool(partial), "notice": "Только записанные в Version изменения доступных полей состояния: до 50 документов и 20 последних версий каждого. Изменения без записи Version здесь отсутствуют; отсутствие строк не означает отсутствия изменений."}
