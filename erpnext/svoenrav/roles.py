# License: GNU General Public License v3. See license.txt
"""Additive native roles. No user is assigned or stripped of roles automatically."""
import frappe

READ = ('read',)
EDIT = ('read','write','create')
POST = ('read','write','create','submit')
COMMON = {name:READ for name in ('Company','Item','UOM','Warehouse','BOM','Work Order','SVOENRAV Specification Snapshot','SVOENRAV Operation Event')}
PROFILES = {
 'SVOENRAV Operator': {**COMMON,'Stock Entry':EDIT,'SVOENRAV Cutting Draft':EDIT,'Stock Entry Type':READ},
 'SVOENRAV Planner': {**COMMON,'Work Order':POST,'Stock Entry':POST,'Stock Reservation Entry':POST,'Bin':READ,'SVOENRAV Cutting Draft':EDIT,'SVOENRAV Production Settings':('read','write'),'SVOENRAV Specification Snapshot':('read','create'),'Stock Entry Type':READ},
 'SVOENRAV Finance': {**COMMON,**{dt:READ for dt in ('Sales Order','Sales Invoice','Payment Entry','Customer','Currency')},'SVOENRAV Payment Allocation':('read','write','create')},
}
PROFILES['SVOENRAV Owner'] = {**PROFILES['SVOENRAV Planner'], **PROFILES['SVOENRAV Finance'], **{dt:POST for dt in ('Sales Order','Purchase Order','Purchase Receipt','Delivery Note','Sales Invoice','Payment Entry','BOM')},'SVOENRAV Specification Snapshot':('read','create'),'SVOENRAV Settings':('read','write'),'Work Order':POST,'Stock Entry':POST,**{dt:READ for dt in ('Account','Cost Center','Mode of Payment','Supplier','Address','Contact','Currency','Customer')}}


def install_profiles():
	from frappe.permissions import add_permission, update_permission_property
	for role, doctypes in PROFILES.items():
		if not frappe.db.exists('Role', role):
			frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':1}).insert()
		for doctype, rights in doctypes.items():
			filters = {'parent':doctype,'role':role,'permlevel':0,'if_owner':0}
			if frappe.db.exists('Custom DocPerm', filters):
				continue  # Preserve the owner's later customisation on migrations.
			add_permission(doctype, role)
			for right in rights:
				update_permission_property(doctype, role, 0, right, 1, validate=False)
		if not frappe.db.exists('Role Profile', role):
			doc = frappe.new_doc('Role Profile');doc.role_profile = role;doc.append('roles', {'role':role});doc.insert()


def simple_default():
	roles = set(frappe.get_roles())
	return 'SVOENRAV Operator' in roles and not roles.intersection({'SVOENRAV Owner','SVOENRAV Planner','SVOENRAV Finance','System Manager'})


def ensure_roles():
	for role in PROFILES:
		if not frappe.db.exists('Role', role):
			frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':1}).insert()
