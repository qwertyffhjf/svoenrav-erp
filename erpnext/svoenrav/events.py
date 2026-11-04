# License: GNU General Public License v3. See license.txt
"""Transactional audit snapshots from trusted lifecycle hooks, including db_set."""
import hashlib
import json
from contextvars import ContextVar
import frappe

INTERNAL = ContextVar('svoenrav_audit_write', default=False)
DOCTYPE = 'SVOENRAV Operation Event'
TRACKED = {'Sales Order','Purchase Order','Work Order','Stock Entry','Purchase Receipt','Delivery Note','Sales Invoice','Payment Entry','Stock Reservation Entry','SVOENRAV Cutting Draft','SVOENRAV Payment Allocation','SVOENRAV Specification Snapshot'}
FIELDS = ('docstatus','status','qty','produced_qty','material_transferred_for_manufacturing','per_delivered','per_billed','reserved_qty','transferred_qty','consumed_qty','delivered_qty','outstanding_amount','advance_paid','amount','input_area','used_area','reusable_area','waste_area','bom_no','production_item','paid_amount','received_amount','payment_type')


def record_event(doc, method=None, deleted=False):
	if doc.doctype not in TRACKED or not doc.get('name') or not frappe.db.exists('DocType', DOCTYPE):
		return
	# A raw server write solely for audit records; never a client-supplied payload.
	# Failure propagates so the originating transaction cannot commit unaudited.
	doc = frappe.get_doc(doc.doctype, doc.name, for_update=True)
	state = {key:doc.get(key) for key in FIELDS if doc.get(key) is not None}
	for field, target, keys in VIRTUAL.get(doc.doctype, []):
		rows = [{key:row.get(key) for key in keys} for row in doc.get(field) or []]
		state[target] = hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()
	if deleted:
		state['deleted'] = True
	payload = json.dumps(state, sort_keys=True, ensure_ascii=False, default=str, separators=(',',':'))
	table = frappe.qb.DocType(DOCTYPE)
	previous = frappe.qb.from_(table).select(table.payload,table.fingerprint).where((table.reference_doctype == doc.doctype) & (table.reference_name == doc.name)).orderby(table.creation, order=frappe.qb.desc).orderby(table.name, order=frappe.qb.desc).limit(1).for_update().run(as_dict=True)
	if previous and previous[0]['payload'] == payload:
		return
	prior_hash = previous[0]['fingerprint'] if previous else ''
	digest = hashlib.sha256((doc.doctype+'\0'+doc.name+'\0'+prior_hash+'\0'+payload).encode()).hexdigest()
	event = frappe.new_doc(DOCTYPE)
	event.update({'reference_doctype':doc.doctype,'reference_name':doc.name,'company':doc.get('company'),'action':method or 'change','payload':payload,'before_payload':previous[0]['payload'] if previous else '{}','fingerprint':digest,'previous_hash':prior_hash,'actor':frappe.session.user})
	token = INTERNAL.set(True)
	try:
		event.insert(ignore_permissions=True)  # Trusted audit service only, cannot be forged through REST.
	finally:
		INTERNAL.reset(token)


VIRTUAL = {
 'Work Order': [('required_items','norms_hash',('item_code','required_qty','stock_uom','operation'))],
 'Payment Entry': [('references','references_hash',('reference_doctype','reference_name','allocated_amount'))],
}


def visible_audit_fields(doctype, fields):
	result = set(fields)
	for field, target, keys in VIRTUAL.get(doctype, []):
		if field in fields and fields[field] is not None and all(all(key in row for key in keys) for row in fields[field]):
			result.add(target)
	return result


def record_deletion(doc, method=None):
	record_event(doc, 'delete', deleted=True)
