# License: GNU General Public License v3. See license.txt
import frappe

from erpnext.svoenrav.cutting_rules import AREA_FIELDS, cutting_balance
from erpnext.svoenrav.flow import validate_source
from erpnext.svoenrav.portal import require_staff


@frappe.whitelist(methods=["POST"])
def evaluate_cutting(work_order, material, area_unit, input_area, used_area, reusable_area, waste_area, skin_reference="", notes=""):
	"""Prepare a validated, unsaved measurement card. No stock documents."""
	require_staff()
	if not frappe.has_permission("SVOENRAV Cutting Draft", ptype="create"):
		frappe.throw("Нет права создавать карточки раскроя.", frappe.PermissionError)
	try:
		work_order = validate_source(work_order)
		material = validate_source(material)
		result = cutting_balance({"area_unit": area_unit, "input_area": input_area, "used_area": used_area, "reusable_area": reusable_area, "waste_area": waste_area})
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	if not isinstance(skin_reference, str) or not isinstance(notes, str):
		frappe.throw("Метка материала и примечание должны быть текстом.", frappe.ValidationError)
	doc = frappe.new_doc("SVOENRAV Cutting Draft")
	doc.update({"work_order": work_order, "material": material, "area_unit": area_unit, "skin_reference": skin_reference, "notes": notes, **{field: result[field] for field in AREA_FIELDS}})
	doc.run_method("validate")
	doc.check_permission("create")
	return {"document": doc.as_dict(), "summary": result, "posted": False}
