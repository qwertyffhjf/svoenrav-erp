# License: GNU General Public License v3. See license.txt
import frappe
from frappe.utils import get_url_to_form

from erpnext.svoenrav.flow import validate_source
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.spec_rules import specification

DOCTYPE = "SVOENRAV Specification Snapshot"


def _order(name):
	try:
		name = validate_source(name)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	order = readable("Work Order", name)
	if order.docstatus != 1:
		frappe.throw("Снимок создаётся для проведённого задания.", frappe.ValidationError)
	return order


@frappe.whitelist()
def get_specification(work_order):
	require_staff()
	order = _order(work_order)
	if not frappe.has_permission(DOCTYPE, ptype="read"):
		frappe.throw("Нет права чтения снимка состава.", frappe.PermissionError)
	rows = frappe.get_list(DOCTYPE, filters={"work_order": order.name}, fields=["name"], limit_page_length=1)
	# Existence alone is not interpreted as permission to read its contents.
	if not rows:
		return {"state": "unavailable" if frappe.db.exists(DOCTYPE, {"work_order": order.name}) else "missing", "can_capture": bool(frappe.has_permission(DOCTYPE, ptype="create"))}
	snapshot = readable(DOCTYPE, rows[0]["name"])
	if not snapshot.get("fingerprint") or not snapshot.get("payload"):
		frappe.throw("Поля снимка недоступны для проверки.", frappe.PermissionError)
	try:
		_, digest = specification(order.as_dict())
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	return {"state": "matches" if digest == snapshot.get("fingerprint") else "changed", "name": snapshot.name, "url": get_url_to_form(DOCTYPE, snapshot.name), "captured_at": snapshot.creation, "fingerprint": snapshot.get("fingerprint"), "payload": snapshot.get("payload"), "notice": "Это нормы задания на момент фиксации, не фактический расход и не полная копия КД/BOM."}


@frappe.whitelist(methods=["POST"])
def capture_specification(work_order):
	require_staff()
	order = _order(work_order)
	if not frappe.has_permission(DOCTYPE, ptype="create"):
		frappe.throw("Нет права фиксации состава.", frappe.PermissionError)
	if frappe.db.exists(DOCTYPE, {"work_order": order.name}):
		return get_specification(order.name)
	doc = frappe.new_doc(DOCTYPE)
	doc.work_order = order.name
	doc.insert()  # Explicit user action, normal permissions, no stock posting.
	return get_specification(order.name)
