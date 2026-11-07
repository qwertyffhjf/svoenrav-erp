# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.products import INTERNAL


class SVOENRAVProductUnit(Document):
	def validate(self):
		if not INTERNAL.get():
			frappe.throw('Карточка экземпляра создаётся и обновляется только проведением или отменой выпуска.', frappe.PermissionError)

	def on_trash(self):
		frappe.throw('Номерные карточки не удаляются; отмена выпуска сохраняет номер.', frappe.ValidationError)

	def before_rename(self, *args, **kwargs):
		frappe.throw('Номер изделия неизменяем.', frappe.ValidationError)
