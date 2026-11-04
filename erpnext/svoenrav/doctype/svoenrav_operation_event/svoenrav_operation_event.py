# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.events import INTERNAL


class SVOENRAVOperationEvent(Document):
	def validate(self):
		if not self.is_new() or not INTERNAL.get():
			frappe.throw('Журнал записывается только серверными обработчиками.', frappe.PermissionError)

	def on_trash(self):
		frappe.throw('Удаление журнала запрещено.', frappe.PermissionError)

	def before_rename(self, *args, **kwargs):
		frappe.throw('Переименование журнала запрещено.', frappe.PermissionError)
