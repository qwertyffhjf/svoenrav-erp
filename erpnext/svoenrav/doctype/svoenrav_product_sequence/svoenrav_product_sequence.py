# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.product_rules import whole, MAX_NUMBER


class SVOENRAVProductSequence(Document):
	def validate(self):
		if self.series_key != 'main':
			frappe.throw('Используется одна общая последовательность main.', frappe.ValidationError)
		try:
			self.next_number = whole(self.next_number, 'Следующий номер', maximum=MAX_NUMBER+1)
			self.digits = whole(self.digits, 'Разрядность', maximum=12)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if not self.get('last_issued') and self.next_number>MAX_NUMBER:
			frappe.throw('Начальный номер за пределами диапазона.', frappe.ValidationError)
		if self.enabled and not self.confirmed:
			frappe.throw('Подтвердите начальный номер по прежнему учёту.', frappe.ValidationError)
		if not self.is_new():
			old = frappe.get_doc(self.doctype, self.name, for_update=True)
			if old.last_issued and (self.next_number != old.next_number or self.digits != old.digits or not self.confirmed):
				frappe.throw('Присвоенные номера и формат нельзя сбрасывать. Можно приостановить нумерацию.', frappe.ValidationError)
			self.last_issued = old.last_issued
		else:
			self.last_issued = 0

	def before_rename(self, *args, **kwargs):
		frappe.throw('Последовательность не переименовывается.', frappe.ValidationError)

	def on_trash(self):
		frappe.throw('Последовательность не удаляется.', frappe.ValidationError)
