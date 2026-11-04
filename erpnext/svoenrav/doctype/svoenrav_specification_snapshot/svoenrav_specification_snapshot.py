# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.specifications import _order
from erpnext.svoenrav.spec_rules import specification


class SVOENRAVSpecificationSnapshot(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw("Снимок состава неизменяем. Для новой версии используйте новое задание.", frappe.ValidationError)
		order = _order(self.work_order)
		try:
			self.payload, self.fingerprint = specification(order.as_dict())
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		self.company = order.company

	def on_trash(self):
		frappe.throw("Удаление зафиксированного состава не поддерживается.", frappe.ValidationError)

	def before_rename(self, *args, **kwargs):
		frappe.throw("Переименование снимка состава не поддерживается.", frappe.ValidationError)
