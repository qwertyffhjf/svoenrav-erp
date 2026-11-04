# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document

from erpnext.svoenrav.queue_rules import normalise_queue


class SVOENRAVProductionSettings(Document):
	def validate(self):
		try:
			items = normalise_queue([row.as_dict() for row in (self.get("queue_items") or [])])
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		for name in items:
			frappe.get_doc("Work Order", name).check_permission("read")
