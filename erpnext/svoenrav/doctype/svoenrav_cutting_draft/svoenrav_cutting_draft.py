# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document

from erpnext.svoenrav.cutting_rules import cutting_balance


class SVOENRAVCuttingDraft(Document):
	def validate(self):
		order = frappe.get_doc("Work Order", self.work_order)
		order.check_permission("read")
		order.apply_fieldlevel_read_permissions()
		if order.docstatus != 1 or order.get("status") in ("Completed", "Closed", "Cancelled", "Stopped"):
			frappe.throw("Раскрой оформляется по действующему проведённому заданию.", frappe.ValidationError)
		if not order.get("company") or not order.get("required_items"):
			frappe.throw("Недостаточно доступных данных задания.", frappe.PermissionError)
		if self.material not in {row.get("item_code") for row in order.required_items}:
			frappe.throw("Материал отсутствует в составе задания.", frappe.ValidationError)
		item = frappe.get_doc("Item", self.material)
		item.check_permission("read")
		item.apply_fieldlevel_read_permissions()
		if item.get("is_stock_item") != 1 or item.get("disabled") != 0:
			frappe.throw("Выберите действующий складской материал.", frappe.ValidationError)
		try:
			result = cutting_balance(self.as_dict())
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if len(self.get("skin_reference") or "") > 140 or len(self.get("notes") or "") > 2000:
			frappe.throw("Метка материала — до 140 символов, примечание — до 2000.", frappe.ValidationError)
		self.company = order.company
		self.consumed_area = result["consumed_area"]
		self.yield_percent = result["yield_percent"]
