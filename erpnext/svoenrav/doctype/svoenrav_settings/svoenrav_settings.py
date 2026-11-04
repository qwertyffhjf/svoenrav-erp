# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext.svoenrav.menu import actions_to_rows, configured_actions, editor_rows, normalise_actions, validate_colour


class SVOENRAVSettings(Document):
	def validate(self):
		try:
			self.brand_colour = validate_colour(self.brand_colour)
			actions = configured_actions(self)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		for action in actions:
			if not frappe.db.exists("DocType", action["doctype"]):
				frappe.throw(f"Тип документа не найден: {action['doctype']}")
		if len(self.brand_name or "") > 80 or len(self.description or "") > 250:
			frappe.throw("Название — до 80 символов, описание — до 250.")


@frappe.whitelist()
def get_menu_editor_rows(kind="current"):
	from erpnext.svoenrav.portal import require_staff

	require_staff()
	settings = frappe.get_single("SVOENRAV Settings")
	settings.check_permission("read")
	if kind not in ("current", "defaults"):
		frappe.throw("Выберите текущее или стандартное меню.", frappe.ValidationError)
	try:
		return editor_rows(settings) if kind == "current" else actions_to_rows(normalise_actions(None))
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
