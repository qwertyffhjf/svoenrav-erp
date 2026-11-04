# License: GNU General Public License v3. See license.txt
import frappe
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.payment_rules import money, reference_share

DOCTYPE = 'SVOENRAV Payment Allocation'


def invoice_orders(name):
	doc = readable('Sales Invoice', name)
	items = doc.get('items')
	if not items:
		frappe.throw('Недоступны строки счёта.', frappe.PermissionError)
	return {row.get('sales_order') or '' for row in items}


def allocations(payment_name, reference_name):
	if not frappe.has_permission(DOCTYPE, ptype='read'):
		return {}, False, []
	table = frappe.qb.DocType(DOCTYPE)
	rows = frappe.qb.from_(table).select(table.name,table.sales_order,table.amount).where((table.payment_entry == payment_name) & (table.payment_reference == reference_name)).limit(501).run(as_dict=True)
	if len(rows) > 500:
		return {}, False, []
	return {row['sales_order']:row['amount'] for row in rows}, True, rows


def enrich_payments(section, order_name):
	if not section['allowed']:
		return section
	totals = {}
	complete = not section['has_more']
	for row in section['rows']:
		row.update(order_amount=None, order_currency=None, allocation_state='unavailable', allocation_references=[], allocation_links=[])
		try:
			doc = readable('Payment Entry', row['name'])
			if doc.get('docstatus') != 1:
				row['allocation_state'] = 'not_submitted'
				continue
			if doc.get('party_type') != 'Customer' or doc.get('payment_type') not in ('Receive','Pay') or doc.get('references') is None:
				raise ValueError('Недоступно распределение')
			currency = doc.get('paid_from_account_currency') if doc.payment_type == 'Receive' else doc.get('paid_to_account_currency')
			if not currency:
				raise ValueError('Недоступна валюта')
			amount, known = money(0), True
			for ref in doc.references:
				kind = ref.get('reference_doctype')
				if kind == 'Sales Invoice':
					orders = invoice_orders(ref.reference_name)
					if order_name not in orders:
						continue
					explicit, _, existing = allocations(doc.name, ref.name)
					for candidate in existing:
						if candidate['sales_order'] == order_name:
							try:
								readable(DOCTYPE, candidate['name'])
								from frappe.utils import get_url_to_form
								row['allocation_links'].append({'name':candidate['name'],'url':get_url_to_form(DOCTYPE,candidate['name'])})
							except frappe.PermissionError:
								explicit.pop(order_name,None)
				else:
					orders, explicit = set(), {}
				share, state = reference_share(ref, order_name, orders, explicit)
				if state == 'needs_split':
					from urllib.parse import urlencode
					row['allocation_references'].append({'reference':ref.name,'url':'/desk/svoenrav-payment-allocation/new-svoenrav-payment-allocation?'+urlencode({'payment_entry':doc.name,'payment_reference':ref.name,'sales_order':order_name})})
				if state == 'needs_split':
					known = False
				elif share is not None:
					amount += share
			if not known:
				row['allocation_state'] = 'needs_split';complete = False;continue
			row.update(order_amount=float(amount), order_currency=currency, allocation_state='exact')
			totals[currency] = totals.get(currency, money(0)) + amount
		except (frappe.PermissionError, ValueError):
			complete = False
	section.update(order_totals={currency:float(value) for currency,value in totals.items()} if complete else None, allocations_complete=complete, note='Доля заказа определяется по точным ссылкам и явным распределениям. Возвраты вычитаются. Итоги разделены по валютам; это распределения Payment Entry, а не полный бухгалтерский баланс. Для смешанного счёта без доли сумма не определяется.')
	return section
