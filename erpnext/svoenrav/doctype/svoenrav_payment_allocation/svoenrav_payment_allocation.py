# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.transactions import lock
from erpnext.svoenrav.payments import invoice_orders
from erpnext.svoenrav.payment_rules import validate_split


class SVOENRAVPaymentAllocation(Document):
	def validate(self):
		lock('Payment Entry', self.payment_entry)
		payment = readable('Payment Entry', self.payment_entry)
		order = readable('Sales Order', self.sales_order)
		if payment.docstatus != 1 or payment.get('party_type') != 'Customer' or payment.get('payment_type') not in ('Receive','Pay') or payment.get('party') != order.get('customer') or payment.get('company') != order.get('company'):
			frappe.throw('Платёж, заказ, компания и покупатель не согласованы.', frappe.ValidationError)
		refs = [row for row in payment.get('references') or [] if row.name == self.payment_reference]
		if len(refs) != 1 or refs[0].reference_doctype != 'Sales Invoice':
			frappe.throw('Выберите строку платежа со смешанным счётом.', frappe.ValidationError)
		ref = refs[0]
		orders = invoice_orders(ref.reference_name)
		if self.sales_order not in orders or orders == {self.sales_order}:
			frappe.throw('Распределение нужно только для счёта с несколькими источниками.', frappe.ValidationError)
		table = frappe.qb.DocType(self.doctype)
		rows = frappe.qb.from_(table).select(table.sales_order, table.amount).where((table.payment_entry == self.payment_entry) & (table.payment_reference == self.payment_reference) & (table.name != (self.get('name') or ''))).for_update().run(as_dict=True)
		if any(row['sales_order'] == self.sales_order for row in rows):
			frappe.throw('Доля этого заказа уже существует.', frappe.ValidationError)
		try:
			self.amount = float(validate_split(ref.allocated_amount, self.amount, [row['amount'] for row in rows]))
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		self.currency = payment.paid_from_account_currency if payment.payment_type == 'Receive' else payment.paid_to_account_currency
		self.company = payment.company

	def on_trash(self):
		frappe.throw('Доли не удаляются. Для отмены распределения установите сумму 0.', frappe.ValidationError)
