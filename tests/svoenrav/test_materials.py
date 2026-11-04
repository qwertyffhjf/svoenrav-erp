import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load_pure(name):
	spec = importlib.util.spec_from_file_location("erpnext.svoenrav." + name, ROOT / f"erpnext/svoenrav/{name}.py")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


rules = load_pure("material_rules")
flow = load_pure("flow")


def material(**extra):
	return {"name":"WOI-1","item_code":"LEATHER","item_name":"Кожа","source_warehouse":"MAIN","stock_uom":"дм²","required_qty":10,"transferred_qty":3,"consumed_qty":1,"returned_qty":0,"stock_reserved_qty":0,**extra}


def balance(**extra):
	return {"known":True,"actual_qty":10,"reserved_stock":3,"stock_uom":"дм²",**extra}


class MaterialRuleTests(unittest.TestCase):
	def assess(self, row=None, stock=None):
		return rules.coverage(rules.group_requirements([row or material()]), {("LEATHER","MAIN"):stock or balance()})

	def test_other_orders_reserves_are_subtracted_once(self):
		result=self.assess()
		self.assertEqual(result["status"],"unreserved")
		self.assertEqual(result["rows"][0]["free"],7)
		self.assertEqual(result["rows"][0]["pending"],7)

	def test_own_reserve_is_added_back_without_exceeding_physical_stock(self):
		result=self.assess(material(stock_reserved_qty=7),balance(reserved_stock=8))
		self.assertEqual(result["status"],"reserved")
		self.assertEqual(result["rows"][0]["usable"],9)
		self.assertEqual(result["rows"][0]["free"],2)

	def test_shortage_is_for_remaining_issue_not_original_bom(self):
		result=self.assess(stock=balance(actual_qty=6,reserved_stock=2))
		self.assertEqual(result["status"],"shortage")
		self.assertEqual(result["rows"][0]["shortage"],3)

	def test_duplicate_rows_share_one_balance(self):
		groups=rules.group_requirements([material(transferred_qty=0),material(name="WOI-2",transferred_qty=0)])
		result=rules.coverage(groups,{("LEATHER","MAIN"):balance(actual_qty=15,reserved_stock=0)})
		self.assertEqual(len(result["rows"]),1)
		self.assertEqual(result["rows"][0]["shortage"],5)

	def test_surplus_on_one_operation_does_not_cover_another(self):
		groups=rules.group_requirements([material(required_qty=3,transferred_qty=6),material(name="WOI-2",required_qty=5,transferred_qty=0)])
		self.assertEqual(groups[0]["pending"],5)

	def test_warehouses_and_uoms_are_not_combined(self):
		self.assertEqual(len(rules.group_requirements([material(),material(source_warehouse="OTHER")])),2)
		with self.assertRaises(ValueError):rules.group_requirements([material(),material(stock_uom="м²")])

	def test_unknown_stock_is_not_zero_or_green(self):
		result=rules.coverage(rules.group_requirements([material()]),{})
		self.assertEqual(result["status"],"review")
		self.assertIsNone(result["rows"][0]["shortage"])
		self.assertIsNone(result["rows"][0]["own_reserved"])

	def test_unreadable_reservations_do_not_become_available_stock(self):
		result=self.assess(material(stock_reserved_qty=7),balance(reservations_known=False,reserved_stock=8))
		self.assertEqual(result["status"],"review")
		self.assertIsNone(result["rows"][0]["shortage"])
		self.assertIsNone(result["rows"][0]["own_reserved"])
		self.assertEqual(result["rows"][0]["free"],2)

	def test_reserve_at_another_warehouse_is_not_credited(self):
		result=self.assess(material(stock_reserved_qty=7),balance(own_reserved=0,reserved_stock=8))
		self.assertEqual(result["rows"][0]["own_reserved"],0)
		self.assertEqual(result["rows"][0]["shortage"],5)

	def test_inconsistent_and_negative_stock_require_review(self):
		for stock in (balance(actual_qty=-1,reserved_stock=0),balance(actual_qty=2,reserved_stock=5),balance(own_reserved=4,reserved_stock=2),balance(stock_uom="м²")):
			with self.subTest(stock=stock):self.assertEqual(self.assess(stock=stock)["status"],"review")

	def test_returned_material_requires_review(self):
		self.assertEqual(self.assess(material(returned_qty=1))["status"],"review")

	def test_fully_issued_does_not_mean_ready_to_release(self):
		self.assertEqual(self.assess(material(transferred_qty=10))["status"],"issued")

	def test_direct_consumption_uses_consumed_quantity(self):
		groups=rules.group_requirements([material(consumed_qty=4)],skip_transfer=True)
		self.assertEqual(groups[0]["pending"],6)

	def test_bad_numbers_and_missing_quantities_are_rejected(self):
		for value in (None,True,-1,"NaN","Infinity","1e999"):
			with self.subTest(value=value),self.assertRaises(ValueError):rules.group_requirements([material(required_qty=value)])

	def test_inputs_are_not_modified(self):
		row=material();original=dict(row);self.assess(row);self.assertEqual(row,original)

	def test_small_shortage_is_not_rounded_into_coverage(self):
		result=self.assess(material(required_qty="0.0000001",transferred_qty=0),balance(actual_qty=0,reserved_stock=0))
		self.assertEqual(result["status"],"shortage")
		self.assertGreater(result["rows"][0]["shortage"],0)


class Document(dict):
	def __init__(self,**kwargs):
		super().__init__(kwargs)
		self.check_permission=Mock()
		self.apply_fieldlevel_read_permissions=Mock()
	def __getattr__(self,key):
		try:return self[key]
		except KeyError:raise AttributeError(key) from None
	def as_dict(self):return dict(self)


def setup_api(*,row=None,stock=None,reservations=None,permissions=None):
	frappe=ModuleType("frappe")
	frappe.PermissionError=PermissionError;frappe.ValidationError=ValueError
	frappe.throw=Mock(side_effect=lambda message,error=ValueError:(_ for _ in ()).throw(error(message)))
	frappe.whitelist=lambda *args,**kwargs:lambda fn:fn
	permissions=permissions or {}
	frappe.has_permission=Mock(side_effect=lambda doctype,ptype="read":permissions.get(doctype,True))
	order=Document(name="WO-1",docstatus=1,status="In Process",skip_transfer=0,company="SVOENRAV",required_items=[Document(**(row or material()))])
	item=Document(stock_uom="дм²",is_stock_item=1,disabled=0,has_serial_no=0,has_batch_no=0)
	warehouse=Document(company="SVOENRAV",is_group=0,disabled=0)
	frappe.get_doc=Mock(side_effect=lambda doctype,name:{"Work Order":order,"Item":item,"Warehouse":warehouse}[doctype])
	frappe.get_list=Mock(side_effect=lambda doctype,**kwargs:stock if doctype=="Bin" else reservations or [])
	frappe.db=Mock();frappe.db.exists.return_value=False;frappe.db.get_single_value.return_value=0
	utils=ModuleType("frappe.utils");utils.now=lambda:"2026-11-04 12:00:00";utils.get_url_to_form=lambda doctype,name:"/desk/work-order/"+name
	portal=ModuleType("erpnext.svoenrav.portal");portal.require_staff=Mock()
	spec=importlib.util.spec_from_file_location("materials_under_test",ROOT/"erpnext/svoenrav/materials.py");api=importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules,{"frappe":frappe,"frappe.utils":utils,"erpnext.svoenrav.flow":flow,"erpnext.svoenrav.material_rules":rules,"erpnext.svoenrav.portal":portal}):spec.loader.exec_module(api)
	return api,frappe,portal,order,item,warehouse


class MaterialAPITests(unittest.TestCase):
	def test_guest_is_blocked_before_any_read(self):
		api,f,p,*_=setup_api();p.require_staff.side_effect=PermissionError
		with self.assertRaises(PermissionError):api.get_material_coverage("WO-1")
		f.get_doc.assert_not_called()

	def test_source_document_permission_is_checked(self):
		api,f,p,order,*_=setup_api();order.check_permission.side_effect=PermissionError
		with self.assertRaises(PermissionError):api.get_material_coverage("WO-1")
		f.get_list.assert_not_called()

	def test_all_source_documents_apply_field_permissions(self):
		api,f,p,order,item,wh=setup_api(stock=[balance()]);result=api.get_material_coverage("WO-1")
		for doc in (order,item,wh):doc.check_permission.assert_called_once_with("read");doc.apply_fieldlevel_read_permissions.assert_called_once()
		self.assertEqual(result["status"],"unreserved")
		self.assertEqual(f.get_list.call_args.args[0],"Bin")
		self.assertNotIn("valuation_rate",f.get_list.call_args.kwargs["fields"])
		self.assertNotIn("ignore_permissions",f.get_list.call_args.kwargs)

	def test_missing_bin_is_zero_but_hidden_bin_is_unknown(self):
		api,f,*_=setup_api(stock=[]);self.assertEqual(api.get_material_coverage("WO-1")["rows"][0]["actual"],0)
		f.db.exists.return_value="hidden-bin"
		result=api.get_material_coverage("WO-1")
		self.assertEqual(result["status"],"review");self.assertIsNone(result["rows"][0]["actual"])

	def test_no_stock_read_permission_means_no_stock_queries(self):
		api,f,*_=setup_api(permissions={"Bin":False})
		self.assertEqual(api.get_material_coverage("WO-1")["status"],"review")
		f.get_list.assert_not_called();f.db.exists.assert_not_called()

	def test_hidden_warehouse_does_not_leak_stock(self):
		api,f,p,order,item,wh=setup_api(stock=[balance()]);wh.check_permission.side_effect=PermissionError
		result=api.get_material_coverage("WO-1")
		self.assertIsNone(result["rows"][0]["warehouse"]);self.assertIsNone(result["rows"][0]["actual"])
		f.get_list.assert_not_called()

	def test_hidden_quantity_is_not_assumed_zero(self):
		api,f,p,order,*_=setup_api(stock=[balance()])
		order.apply_fieldlevel_read_permissions.side_effect=lambda:order["required_items"][0].pop("required_qty")
		with self.assertRaises(ValueError):api.get_material_coverage("WO-1")
		f.get_list.assert_not_called()

	def test_exact_reservations_at_other_warehouse_are_not_credited(self):
		sre={"voucher_detail_no":"WOI-1","item_code":"LEATHER","warehouse":"OTHER","reserved_qty":7,"delivered_qty":0,"transferred_qty":0,"consumed_qty":0}
		api,f,*_=setup_api(row=material(stock_reserved_qty=7),stock=[balance(reserved_stock=8)],reservations=[sre])
		result=api.get_material_coverage("WO-1")
		self.assertEqual(result["rows"][0]["own_reserved"],0);self.assertEqual(result["rows"][0]["shortage"],5)
		call=f.get_list.call_args_list[0];self.assertEqual(call.kwargs["filters"]["voucher_no"],"WO-1")

	def test_incomplete_reservation_visibility_requires_review(self):
		api,f,*_=setup_api(row=material(stock_reserved_qty=7),stock=[balance(reserved_stock=8)],reservations=[])
		result=api.get_material_coverage("WO-1")
		self.assertEqual(result["status"],"review");self.assertIsNone(result["rows"][0]["own_reserved"])

	def test_no_reservation_read_permission_does_not_add_voucher_total(self):
		api,f,*_=setup_api(row=material(stock_reserved_qty=7),stock=[balance(reserved_stock=8)],permissions={"Stock Reservation Entry":False})
		result=api.get_material_coverage("WO-1")
		self.assertEqual(result["status"],"review");self.assertIsNone(result["rows"][0]["shortage"])

	def test_serialized_and_special_production_is_not_marked_ready(self):
		api,f,p,order,item,*_=setup_api(stock=[balance()]);item["has_batch_no"]=1
		self.assertEqual(api.get_material_coverage("WO-1")["status"],"review")
		item["has_batch_no"]=0;order["track_semi_finished_goods"]=1
		self.assertTrue(api.get_material_coverage("WO-1")["review_required"])

	def test_completed_work_order_is_rejected(self):
		api,f,p,order,*_=setup_api();order["status"]="Completed"
		with self.assertRaises(ValueError):api.get_material_coverage("WO-1")
		f.get_list.assert_not_called()
