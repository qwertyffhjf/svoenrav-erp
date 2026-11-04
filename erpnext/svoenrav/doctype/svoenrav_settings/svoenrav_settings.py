# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext.svoenrav.menu import normalise_actions, validate_colour


class SVOENRAVSettings(Document):
	def validate(self):
		try:
			self.brand_colour = validate_colour(self.brand_colour)
			actions = normalise_actions(self.actions_json)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		for action in actions:
			if not frappe.db.exists("DocType", action["doctype"]):
				frappe.throw(f"Тип документа не найден: {action['doctype']}")
		if len(self.brand_name or "") > 80 or len(self.description or "") > 250:
			frappe.throw("Название — до 80 символов, описание — до 250.")
