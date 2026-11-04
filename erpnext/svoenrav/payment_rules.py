# License: GNU General Public License v3. See license.txt
from decimal import Decimal, InvalidOperation


def money(value):
	if value is None or isinstance(value, bool):
		raise ValueError("Недоступна сумма.")
	try:
		amount = Decimal(str(value))
	except InvalidOperation:
		raise ValueError("Некорректная сумма.") from None
	if not amount.is_finite() or abs(amount) > Decimal('1e15'):
		raise ValueError("Некорректная сумма.")
	return amount


def validate_split(reference_amount, amount, others):
	limit, value = money(reference_amount), money(amount)
	if not limit or (value and (value > 0) != (limit > 0)):
		raise ValueError("Доля должна иметь тот же знак, что и распределение платежа.")
	all_values = [money(item) for item in others]
	if any(item and (item > 0) != (limit > 0) for item in all_values) or abs(value) + sum(abs(item) for item in all_values) > abs(limit):
		raise ValueError("Сумма долей превышает распределение платежа.")
	return value


def reference_share(reference, order, invoice_orders, explicit):
	"""Only exact links or explicit allocations, never a guessed invoice ratio."""
	amount = money(reference.get('allocated_amount'))
	if reference.get('reference_doctype') == 'Sales Order':
		return (amount, 'direct') if reference.get('reference_name') == order else (None, 'unrelated')
	if reference.get('reference_doctype') != 'Sales Invoice' or order not in invoice_orders:
		return None, 'unrelated'
	if invoice_orders == {order}:
		return amount, 'invoice'
	if amount == 0:
		return amount, 'invoice_zero'
	if order not in explicit:
		return None, 'needs_split'
	return validate_split(amount, explicit[order], [v for k,v in explicit.items() if k != order]), 'explicit'
