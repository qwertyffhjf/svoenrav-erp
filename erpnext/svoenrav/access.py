# License: GNU General Public License v3. See license.txt
"""Stored snapshots never grant access to a protected source or field."""
import json
import frappe
from erpnext.svoenrav.flow import visible_dict
from erpnext.svoenrav.events import visible_audit_fields


def event_permission(doc, ptype=None, user=None, **kwargs):
	if ptype not in (None,'read','select','print','export'):
		return False
	try:
		source = frappe.get_doc(doc.reference_doctype, doc.reference_name)
		if not frappe.has_permission(source.doctype, 'read', doc=source, user=user):
			return False
		source.apply_fieldlevel_read_permissions()
		return (set(json.loads(doc.payload or '{}')) | set(json.loads(doc.get('before_payload') or '{}'))).issubset(visible_audit_fields(source.doctype,visible_dict(source)))
	except (frappe.DoesNotExistError, ValueError):
		return False


def snapshot_permission(doc, ptype=None, user=None, **kwargs):
	if ptype not in (None,'read','select','print','export'):
		return True  # Does not grant permission: normal role rules still apply.
	try:
		source = frappe.get_doc('Work Order', doc.work_order)
		if not frappe.has_permission('Work Order','read',doc=source,user=user):
			return False
		source.apply_fieldlevel_read_permissions()
		from erpnext.svoenrav.spec_rules import specification
		specification(visible_dict(source))  # Fail closed on inaccessible normative fields.
		for name, stored in json.loads(doc.get('pack') or '{}').get('boms', {}).items():
			bom = frappe.get_doc('BOM', name)
			if not frappe.has_permission('BOM','read',doc=bom,user=user):
				return False
			bom.apply_fieldlevel_read_permissions()
			readable = visible_dict(bom)
			for field in ('item','quantity','uom','items','operations'):
				if stored.get(field) is not None and field not in readable:
					return False
			for field in ('items','operations'):
				current_rows = readable.get(field) or []
				allowed = set(current_rows[0]) if current_rows else set()
				if any(any(k not in allowed for k,v in row.items() if v is not None) for row in stored.get(field) or []):
					return False
		return True
	except (frappe.DoesNotExistError, ValueError):
		return False


def event_query(user=None):
	# Listing payloads is intentionally denied. The API checks each source and
	# filters every field before returning audit rows. Direct Form uses has_permission.
	return '1=0'


def snapshot_query(user=None):
	# Source-level checks are applied on every direct read/API; prevent bulk payload exports.
	return '1=0'


def allocation_permission(doc, ptype=None, user=None, **kwargs):
	if ptype == 'create':
		return True  # Controller verifies both sources before accepting any split.
	for doctype, field in (('Payment Entry','payment_entry'),('Sales Order','sales_order')):
		if not doc.get(field):
			return False
		try:
			source = frappe.get_doc(doctype, doc.get(field))
			if not frappe.has_permission(doctype,'read',doc=source,user=user):
				return False
		except frappe.DoesNotExistError:
			return False
	return True
