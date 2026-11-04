# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt

from urllib.parse import urlencode

import frappe
from frappe.utils import get_url_to_form, get_url_to_list

from erpnext.svoenrav.menu import configured_actions, validate_colour
from erpnext.svoenrav.flow import OPERATIONS


def require_staff():
	if frappe.session.user == "Guest":
		frappe.redirect("/login?" + urlencode({"redirect-to": "/svoenrav"}))
	if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		frappe.throw("Доступно только сотрудникам мастерской.", frappe.PermissionError)


def get_page_context():
	require_staff()
	settings = frappe.get_single("SVOENRAV Settings")
	try:
		actions = configured_actions(settings)
		colour = validate_colour(settings.brand_colour)
	except ValueError:
		# Fail visibly rather than silently replacing a saved menu with defaults.
		frappe.throw("Проверьте настройки стартовой страницы SVOENRAV.", frappe.ValidationError)
	visible = []
	action_warnings = []
	for action in actions:
		if not frappe.db.exists("DocType", action["doctype"]):
			continue
		permission = "create" if action["mode"] == "new" else "read"
		if not frappe.has_permission(action["doctype"], ptype=permission):
			continue
		if action.get("operation"):
			spec = OPERATIONS[action["operation"]]
			if not frappe.has_permission(spec["source"], ptype="read"):
				continue
			visible.append({**action, "url": "/desk/svoenrav-workshop?" + urlencode({"operation": action["operation"]})})
			continue
		meta = frappe.get_meta(action["doctype"])
		if action["mode"] == "new" and not meta.issingle:
			name = "new-" + frappe.scrub(action["doctype"]).replace("_", "-")
			url = get_url_to_form(action["doctype"], name)
		else:
			url = get_url_to_list(action["doctype"])
		if action.get("defaults"):
			# Setup fixtures translate Stock Entry Type names. Resolve the standard
			# type by its stable purpose instead of assuming its English name exists.
			types = []
			if frappe.has_permission("Stock Entry Type", ptype="read"):
				types = frappe.get_list(
					"Stock Entry Type",
					filters={"purpose": action["defaults"]["stock_entry_type"], "is_standard": 1},
					fields=["name"],
					order_by="name asc",
					limit_page_length=1,
				)
			if not types:
				action_warnings.append("Действие «" + action["label"] + "» недоступно: проверьте стандартные типы складских операций и права доступа.")
				continue
			url += "?" + urlencode({"stock_entry_type": types[0]["name"]})
		visible.append({**action, "url": url})
	work_orders = []
	can_read_work_orders = frappe.has_permission("Work Order", ptype="read")
	if can_read_work_orders:
		work_orders = frappe.get_list(
			"Work Order",
			filters={"docstatus": 1, "status": ["not in", ["Completed", "Stopped", "Closed", "Cancelled"]]},
			fields=["name", "item_name", "qty", "produced_qty", "status", "expected_delivery_date"],
			order_by="expected_delivery_date asc, creation asc",
			limit_page_length=8,
		)
		for order in work_orders:
			order["url"] = get_url_to_form("Work Order", order["name"])
	return {
		"brand_name": settings.brand_name or "SVOENRAV",
		"brand_description": settings.description or "Кожевенная мастерская",
		"brand_colour": colour,
		"actions": visible,
		"action_warnings": action_warnings,
		"quick_actions": [action for action in visible if action.get("section") == "quick"],
		"module_actions": [action for action in visible if action.get("section") != "quick"],
		"work_orders": work_orders,
		"can_read_work_orders": can_read_work_orders,
		"workshop_url": "/desk/svoenrav-workshop",
		"can_read_orders": bool(frappe.has_permission("Sales Order", ptype="read")),
		"can_configure": "System Manager" in frappe.get_roles(),
		"settings_url": get_url_to_form("SVOENRAV Settings"),
		"customise_url": get_url_to_form("Customize Form"),
	}
