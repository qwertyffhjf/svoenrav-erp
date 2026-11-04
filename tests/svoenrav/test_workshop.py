import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class Document(dict):
	def __init__(self, **values):
		super().__init__(values)
		self.check_permission = Mock()
		self.apply_fieldlevel_read_permissions = Mock()
		self.insert = Mock()
		self.save = Mock()
		self.submit = Mock()

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError:
			raise AttributeError(name) from None

	def as_dict(self):
		return dict(self)

	def is_new(self):
		return self.get("__islocal", True)


def setup_api(*, permissions=None, source=None, target=None):
	permissions = permissions or {}
	frappe = ModuleType("frappe")
	frappe.ValidationError = ValueError
	frappe.PermissionError = PermissionError
	frappe.throw = Mock(side_effect=lambda message, error=ValueError: (_ for _ in ()).throw(error(message)))
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.has_permission = Mock(side_effect=lambda doctype, ptype="read": permissions.get((doctype, ptype), permissions.get((doctype, "create"), False) if ptype == "read" and doctype in ("Stock Entry", "Purchase Receipt", "Delivery Note") else False))
	frappe.get_list = Mock(return_value=[])
	frappe.db = Mock()
	frappe.db.get_single_value.return_value = False
	frappe.db.exists.return_value = False
	frappe.get_doc = Mock(side_effect=lambda *args: target if isinstance(args[0], dict) else source)
	utils = ModuleType("frappe.utils")
	utils.get_url_to_form = lambda doctype, name: "/desk/" + doctype.lower().replace(" ", "-") + "/" + name
	portal = ModuleType("erpnext.svoenrav.portal")
	portal.require_staff = Mock()
	flow_spec = importlib.util.spec_from_file_location("erpnext.svoenrav.flow", ROOT / "erpnext/svoenrav/flow.py")
	flow = importlib.util.module_from_spec(flow_spec)
	flow_spec.loader.exec_module(flow)
	factories = {}
	modules = {"frappe": frappe, "frappe.utils": utils, "erpnext.svoenrav.portal": portal, "erpnext.svoenrav.flow": flow}
	for module, function in (
		("erpnext.buying.doctype.purchase_order.purchase_order", "make_purchase_receipt"),
		("erpnext.selling.doctype.sales_order.sales_order", "make_delivery_note"),
		("erpnext.manufacturing.doctype.work_order.work_order", "make_stock_entry"),
	):
		stub = ModuleType(module)
		factories[function] = Mock(return_value=target)
		setattr(stub, function, factories[function])
		modules[module] = stub
	factory_patch = patch.dict(sys.modules, modules)
	factory_patch.start()
	spec = importlib.util.spec_from_file_location("workshop_under_test", ROOT / "erpnext/svoenrav/workshop.py")
	api = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(api)
	return api, frappe, portal, factories, factory_patch


class WorkshopTests(unittest.TestCase):
	def api(self, **kwargs):
		api, frappe, portal, factories, factory_patch = setup_api(**kwargs)
		self.addCleanup(factory_patch.stop)
		return api, frappe, portal, factories

	def work_order(self, **changes):
		return Document(name="WO-1", docstatus=1, status="In Process", qty=10, produced_qty=2, material_transferred_for_manufacturing=6, **changes)

	def test_options_do_not_offer_operations_without_both_permissions(self):
		api, frappe, portal, factories = self.api(permissions={("Stock Entry", "create"): True})
		self.assertEqual(api.get_options()["operations"], [])
		portal.require_staff.assert_called_once()

	def test_unauthorized_source_blocks_before_factory(self):
		source = self.work_order()
		source.check_permission.side_effect = PermissionError
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "create"): True}, source=source)
		with self.assertRaises(PermissionError):
			api.prepare_operation("manufacture", "WO-1", 1)
		factories["make_stock_entry"].assert_not_called()

	def test_missing_create_permission_blocks_before_source_read(self):
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True})
		with self.assertRaises(PermissionError):
			api.prepare_operation("manufacture", "WO-1", 1)
		frappe.get_doc.assert_not_called()

	def test_guest_guard_runs_before_any_queries(self):
		api, frappe, portal, factories = self.api()
		portal.require_staff.side_effect = PermissionError
		for callback in (api.get_options, lambda: api.prepare_operation("receipt", "PO-1"), lambda: api.get_order_card("SO-1")):
			with self.assertRaises(PermissionError):
				callback()
		frappe.get_doc.assert_not_called()
		frappe.get_list.assert_not_called()

	def test_manufacture_uses_native_factory_without_saving_or_submitting(self):
		source = self.work_order()
		target = Document(doctype="Stock Entry", docstatus=0, items=[{"item_code": "BAG"}])
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "create"): True}, source=source, target=target)
		factories["make_stock_entry"].return_value = target.as_dict()
		result = api.prepare_operation("manufacture", "WO-1", "2.5")
		self.assertEqual(result["doctype"], "Stock Entry")
		factories["make_stock_entry"].assert_called_once_with("WO-1", "Manufacture", qty=2.5)
		source.check_permission.assert_called_once_with("read")
		target.check_permission.assert_called_once_with("create")
		for doc in (source, target):
			doc.insert.assert_not_called()
			doc.save.assert_not_called()
			doc.submit.assert_not_called()

	def test_mixed_consumption_scheme_is_blocked_even_after_setting_changes(self):
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "create"): True}, source=self.work_order())
		frappe.db.exists.return_value = "SE-previous-consumption"
		with self.assertRaises(ValueError):
			api.prepare_operation("manufacture", "WO-1", 1)
		factories["make_stock_entry"].assert_not_called()

	def test_invalid_production_qty_is_blocked_before_native_factory(self):
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "create"): True}, source=self.work_order())
		for quantity in ("NaN", -1, 5):
			with self.subTest(quantity=quantity), self.assertRaises(ValueError):
				api.prepare_operation("manufacture", "WO-1", quantity)
		factories["make_stock_entry"].assert_not_called()

	def test_receipt_and_delivery_use_native_mapping_and_preserve_links(self):
		for operation, source_type, target_type, factory in (
			("receipt", "Purchase Order", "Purchase Receipt", "make_purchase_receipt"),
			("delivery", "Sales Order", "Delivery Note", "make_delivery_note"),
		):
			with self.subTest(operation=operation):
				source = Document(name="SOURCE-1", docstatus=1, status="To Receive")
				target = Document(doctype=target_type, docstatus=0, items=[{"source_detail": "ROW-1"}])
				api, frappe, portal, factories = self.api(permissions={(source_type, "read"): True, (target_type, "create"): True}, source=source, target=target)
				result = api.prepare_operation(operation, "SOURCE-1")
				self.assertEqual(result["items"][0]["source_detail"], "ROW-1")
				factories[factory].assert_called_once_with("SOURCE-1")
				target.submit.assert_not_called()

	def test_empty_wrong_or_saved_target_is_rejected(self):
		for extra in ({"items": []}, {"doctype": "Sales Invoice"}, {"docstatus": 1}, {"__islocal": False}):
			with self.subTest(extra=extra):
				target = Document(**{"doctype": "Purchase Receipt", "docstatus": 0, "items": [{}], **extra})
				api, frappe, portal, factories = self.api(permissions={("Purchase Order", "read"): True, ("Purchase Receipt", "create"): True}, source=Document(name="PO-1", docstatus=1), target=target)
				with self.assertRaises(ValueError):
					api.prepare_operation("receipt", "PO-1")

	def test_related_lists_are_permission_aware_and_report_truncation(self):
		api, frappe, portal, factories = self.api(permissions={("Delivery Note", "read"): True})
		frappe.get_list.return_value = [{"name": f"DN-{i}", "docstatus": 1} for i in range(21)]
		section = api._related("Delivery Note", [["Delivery Note Item", "against_sales_order", "=", "SO-1"]], ["posting_date"])
		self.assertTrue(section["has_more"])
		self.assertEqual(len(section["rows"]), 20)
		self.assertNotIn("ignore_permissions", frappe.get_list.call_args.kwargs)
		self.assertIn("modified", frappe.get_list.call_args.kwargs["fields"])
		self.assertFalse(api._related("Sales Invoice", {}, ["grand_total"])["allowed"])
		self.assertEqual(frappe.get_list.call_count, 1)

	def test_order_card_never_returns_unrelated_or_forbidden_financial_documents(self):
		source = Document(name="SO-1", customer_name="Покупатель", items=[])
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "read"): True, ("Delivery Note", "read"): True}, source=source)
		def query(doctype, **kwargs):
			if doctype == "Work Order" and kwargs.get("pluck"):
				self.assertEqual(kwargs["filters"], {"sales_order": "SO-1"})
				return ["WO-1"]
			if doctype == "Stock Entry":
				self.assertEqual(kwargs["filters"], {"work_order": ["in", ["WO-1"]]})
			if doctype == "Delivery Note":
				self.assertEqual(kwargs["filters"], [["Delivery Note Item", "against_sales_order", "=", "SO-1"]])
			return []
		frappe.get_list.side_effect = query
		result = api.get_order_card("SO-1")
		source.check_permission.assert_called_once_with("read")
		self.assertFalse(result["invoices"]["allowed"])
		self.assertNotIn("Sales Invoice", [call.args[0] for call in frappe.get_list.call_args_list])

	def test_unknown_operation_or_unexpected_quantity_cannot_choose_arbitrary_mapper(self):
		api, frappe, portal, factories = self.api(permissions={("Purchase Order", "read"): True, ("Purchase Receipt", "create"): True}, source=Document(name="PO-1", docstatus=1))
		for operation in ("delete", "Sales Invoice", None):
			with self.subTest(operation=operation), self.assertRaises(ValueError):
				api.prepare_operation(operation, "PO-1")
		with self.assertRaises(ValueError):
			api.prepare_operation("receipt", "PO-1", 1)
		for factory in factories.values():
			factory.assert_not_called()

	def test_large_order_does_not_present_partial_stock_history_as_complete(self):
		api, frappe, portal, factories = self.api(permissions={("Work Order", "read"): True, ("Stock Entry", "read"): True}, source=Document(name="SO-LARGE", items=[]))
		frappe.get_list.side_effect = lambda doctype, **kwargs: [f"WO-{i}" for i in range(501)] if kwargs.get("pluck") else []
		result = api.get_order_card("SO-LARGE")
		self.assertTrue(result["stock"]["has_more"])
		self.assertEqual(result["stock"]["rows"], [])
		self.assertTrue(result["stock"]["note"])
		self.assertNotIn("Stock Entry", [call.args[0] for call in frappe.get_list.call_args_list])

	def test_existing_draft_stops_factory_and_has_no_stock_side_effects(self):
		source=self.work_order()
		api,f,p,factories=self.api(permissions={("Work Order","read"):True,("Stock Entry","create"):True},source=source)
		f.get_list.return_value=[{"name":"SE-DRAFT","docstatus":0}]
		result=api.prepare_operation("transfer","WO-1",1)
		self.assertEqual(result["existing_drafts"]["rows"][0]["name"],"SE-DRAFT")
		self.assertEqual(f.get_list.call_args.kwargs['filters'],{"work_order":"WO-1","purpose":"Material Transfer for Manufacture","docstatus":0})
		factories['make_stock_entry'].assert_not_called()

	def test_short_path_requires_read_permission_for_draft_detection(self):
		api,f,p,factories=self.api(permissions={("Work Order","read"):True,("Stock Entry","create"):True,("Stock Entry","read"):False},source=self.work_order())
		with self.assertRaises(PermissionError):api.prepare_operation('transfer','WO-1',1)
		factories['make_stock_entry'].assert_not_called();f.get_list.assert_not_called()

	def test_receipt_and_delivery_drafts_use_exact_parent_and_child_link(self):
		for operation,source_type,target,child,field in [('receipt','Purchase Order','Purchase Receipt','Purchase Receipt Item','purchase_order'),('delivery','Sales Order','Delivery Note','Delivery Note Item','against_sales_order')]:
			api,f,p,_=self.api(permissions={(source_type,'read'):True,(target,'create'):True},source=Document(name='SRC',docstatus=1))
			api.get_operation_drafts(operation,'SRC')
			self.assertEqual(f.get_list.call_args.kwargs['filters'],[[target,'docstatus','=',0],[child,field,'=','SRC']])

	def test_payments_only_follow_readable_invoices_deduplicate_and_do_not_total(self):
		api,f,p,_=self.api(permissions={('Payment Entry','read'):True})
		f.get_list.return_value=[{'name':'PAY-1','docstatus':1,'modified':'2026-11-04'}]
		result=api._payments('SO-1',{'rows':[{'name':'INV-VISIBLE'}],'has_more':True})
		self.assertEqual(len(result['rows']),1);self.assertTrue(result['has_more'])
		filters=[c.kwargs['filters'] for c in f.get_list.call_args_list]
		self.assertEqual(filters[1][1],['Payment Entry Reference','reference_name','=','INV-VISIBLE'])
		self.assertNotIn('total',result)

	def test_payment_denial_does_not_query_payment_rows(self):
		api,f,p,_=self.api()
		result=api._payments('SO-1',{'rows':[],'has_more':False})
		self.assertFalse(result['allowed']);self.assertEqual(result['rows'],[]);f.get_list.assert_not_called()

	def test_specification_mismatch_blocks_short_path(self):
		api,f,p,_=self.api(permissions={('SVOENRAV Specification Snapshot','read'):True})
		f.db.exists.return_value=True;f.get_list.return_value=[{'name':'SNAP'}]
		f.get_doc.side_effect=None;f.get_doc.return_value=Document(name='SNAP',fingerprint='wrong')
		spec=importlib.util.spec_from_file_location('svspec',ROOT/'erpnext/svoenrav/spec_rules.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
		source=Document(name='WO-1',company='C',production_item='BAG',bom_no='BOM1',stock_uom='шт',qty=1,required_items=[{'item_code':'L','stock_uom':'дм²','required_qty':10}])
		with patch.dict(sys.modules,{'erpnext.svoenrav.spec_rules':module}), self.assertRaises(ValueError):api._check_specification(source)

	def test_snapshot_existence_is_not_permission_to_read(self):
		api,f,p,_=self.api();f.db.exists.return_value=True
		with self.assertRaises(PermissionError):api._check_specification(self.work_order())
		f.get_list.assert_not_called()

	def test_unchanged_snapshot_allows_short_path_check(self):
		api,f,p,_=self.api(permissions={('SVOENRAV Specification Snapshot','read'):True})
		module_spec=importlib.util.spec_from_file_location('svspec',ROOT/'erpnext/svoenrav/spec_rules.py');module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
		source=Document(name='WO-1',company='C',production_item='BAG',bom_no='BOM1',stock_uom='шт',qty=1,required_items=[{'item_code':'L','stock_uom':'дм²','required_qty':10}])
		f.db.exists.return_value=True;f.get_list.return_value=[{'name':'SNAP'}]
		f.get_doc.side_effect=None;f.get_doc.return_value=Document(name='SNAP',fingerprint=module.specification(source.as_dict())[1])
		with patch.dict(sys.modules,{'erpnext.svoenrav.spec_rules':module}):api._check_specification(source)
