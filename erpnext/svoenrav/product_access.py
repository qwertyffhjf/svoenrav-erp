# License: GNU General Public License v3. See license.txt
import frappe


def model_permission(doc, ptype=None, user=None, **kwargs):
	if ptype=='create':
		return True  # Normal roles + controller validates selected Item.
	if not doc.get('item_code'):
		return False
	try:
		item=frappe.get_doc('Item',doc.item_code)
		return bool(frappe.has_permission('Item','read',doc=item,user=user))
	except frappe.DoesNotExistError:
		return False


def unit_permission(doc, ptype=None, user=None, **kwargs):
	if ptype not in (None,'read','select','print','export'):
		return False
	try:
		for field,doctype in (('manufacture_entry','Stock Entry'),('model','SVOENRAV Model'),('item_code','Item')):
			source=frappe.get_doc(doctype,doc.get(field))
			if not frappe.has_permission(doctype,'read',doc=source,user=user):
				return False
		# Direct Forms must not disclose optional links hidden from the current user.
		optional=[('work_order','Work Order')]
		if 1 in doc.meta.get_permlevel_access('read', user=user):
			optional += [('sales_order','Sales Order')]
			if doc.get('native_serial_no') and frappe.db.exists('Serial No',doc.native_serial_no):
				optional += [('native_serial_no','Serial No')]
		for field,doctype in optional:
			if doc.get(field) and not frappe.has_permission(doctype,'read',doc=frappe.get_doc(doctype,doc.get(field)),user=user):
				return False
		return True
	except frappe.DoesNotExistError:
		return False
