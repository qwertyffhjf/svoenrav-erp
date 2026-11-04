import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


def load(name,path):
	spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


rules=load("erpnext.svoenrav.cutting_rules","erpnext/svoenrav/cutting_rules.py")
flow=load("erpnext.svoenrav.flow","erpnext/svoenrav/flow.py")


def values(**extra):
	return {"work_order":"WO-1","material":"LEATHER","area_unit":"дм²","input_area":20,"used_area":12,"reusable_area":6,"waste_area":2,**extra}


class CuttingRulesTests(unittest.TestCase):
	def test_balanced_area_and_yield(self):
		result=rules.cutting_balance(values())
		self.assertEqual(result["consumed_area"],14)
		self.assertEqual(result["yield_percent"],60)

	def test_decimal_addition_is_exact(self):
		result=rules.cutting_balance(values(input_area="0.3",used_area="0.1",reusable_area="0.1",waste_area="0.1"))
		self.assertTrue(result["balanced"])

	def test_imbalance_is_rejected_without_tolerance_assumptions(self):
		with self.assertRaises(ValueError):rules.cutting_balance(values(waste_area="2.000001"))

	def test_unknown_unit_is_not_converted(self):
		for unit in (None,"","шт","m2"):
			with self.subTest(unit=unit),self.assertRaises(ValueError):rules.cutting_balance(values(area_unit=unit))

	def test_invalid_and_overprecise_areas_are_rejected(self):
		for number in (None,True,-1,"NaN","Infinity","1e-7",1000000001):
			with self.subTest(number=number),self.assertRaises(ValueError):rules.cutting_balance(values(used_area=number))

	def test_zero_input_is_not_a_cutting(self):
		with self.assertRaises(ValueError):rules.cutting_balance(values(input_area=0,used_area=0,reusable_area=0,waste_area=0))

	def test_full_reusable_remainder_is_allowed_and_not_a_stock_return(self):
		result=rules.cutting_balance(values(used_area=0,reusable_area=20,waste_area=0))
		self.assertEqual(result["consumed_area"],0)


class Doc(dict):
	def __init__(self,**kwargs):
		super().__init__(kwargs);self.check_permission=Mock();self.apply_fieldlevel_read_permissions=Mock();self.insert=Mock();self.save=Mock();self.submit=Mock()
	def __getattr__(self,key):
		try:return self[key]
		except KeyError:raise AttributeError(key) from None
	def __setattr__(self,key,value):
		if key in ("company","consumed_area","yield_percent"):self[key]=value
		else:object.__setattr__(self,key,value)
	def as_dict(self):return dict(self)
	def run_method(self,name):return getattr(self,name)()


def setup():
	frappe=ModuleType("frappe");frappe.PermissionError=PermissionError;frappe.ValidationError=ValueError
	frappe.whitelist=lambda *args,**kwargs:lambda fn:fn
	frappe.throw=Mock(side_effect=lambda text,error=ValueError:(_ for _ in ()).throw(error(text)))
	frappe.has_permission=Mock(return_value=True)
	order=Doc(name="WO-1",docstatus=1,status="In Process",company="COMPANY",required_items=[Doc(item_code="LEATHER")])
	item=Doc(is_stock_item=1,disabled=0)
	frappe.get_doc=Mock(side_effect=lambda doctype,name:order if doctype=="Work Order" else item)
	portal=ModuleType("erpnext.svoenrav.portal");portal.require_staff=Mock()
	document=ModuleType("frappe.model.document");document.Document=Doc
	context=patch.dict(sys.modules,{"frappe":frappe,"frappe.model.document":document,"erpnext.svoenrav.cutting_rules":rules,"erpnext.svoenrav.flow":flow,"erpnext.svoenrav.portal":portal});context.start()
	controller=load("cutting_controller","erpnext/svoenrav/doctype/svoenrav_cutting_draft/svoenrav_cutting_draft.py")
	frappe.new_doc=Mock(side_effect=lambda doctype:controller.SVOENRAVCuttingDraft(doctype=doctype,docstatus=0))
	api=load("cutting_api","erpnext/svoenrav/cutting.py")
	return api,frappe,portal,order,item,controller,context


class CuttingAPITests(unittest.TestCase):
	def api(self):
		api,f,p,order,item,controller,context=setup();self.addCleanup(context.stop);return api,f,p,order,item,controller

	def test_balanced_card_is_prepared_without_save_or_submit(self):
		api,f,*_=self.api();result=api.evaluate_cutting(**values())
		self.assertFalse(result["posted"])
		self.assertEqual(result["document"]["company"],"COMPANY")
		self.assertEqual(result["document"]["yield_percent"],60)
		# The endpoint returns data; it never persists the prepared Document.
		self.assertEqual(result["document"]["docstatus"],0)

	def test_guest_and_missing_create_permission_are_blocked(self):
		api,f,p,*_=self.api();p.require_staff.side_effect=PermissionError
		with self.assertRaises(PermissionError):api.evaluate_cutting(**values())
		f.new_doc.assert_not_called();p.require_staff.side_effect=None;f.has_permission.return_value=False
		with self.assertRaises(PermissionError):api.evaluate_cutting(**values())
		f.new_doc.assert_not_called()

	def test_bad_balance_is_blocked_before_document_creation(self):
		api,f,*_=self.api()
		with self.assertRaises(ValueError):api.evaluate_cutting(**values(waste_area=3))
		f.new_doc.assert_not_called()

	def test_material_must_belong_to_source_order(self):
		api,f,*_=self.api()
		with self.assertRaises(ValueError):api.evaluate_cutting(**values(material="OTHER"))

	def test_source_permissions_are_checked(self):
		api,f,p,order,*_=self.api();order.check_permission.side_effect=PermissionError
		with self.assertRaises(PermissionError):api.evaluate_cutting(**values())

	def test_direct_form_validation_rejects_wrong_balance(self):
		api,f,p,order,item,controller=self.api();doc=controller.SVOENRAVCuttingDraft(**values(waste_area=3))
		with self.assertRaises(ValueError):doc.validate()

	def test_company_is_derived_from_order_not_client(self):
		api,f,p,order,item,controller=self.api();doc=controller.SVOENRAVCuttingDraft(**values(),company="OTHER")
		doc.validate();self.assertEqual(doc.company,"COMPANY")

	def test_card_schema_cannot_be_submitted_as_stock_operation(self):
		schema=json.loads((ROOT/"erpnext/svoenrav/doctype/svoenrav_cutting_draft/svoenrav_cutting_draft.json").read_text())
		self.assertEqual(schema["is_submittable"],0)
		self.assertNotIn("Stock Entry",str(schema["fields"]))
