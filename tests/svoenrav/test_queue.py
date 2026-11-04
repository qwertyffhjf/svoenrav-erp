import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("erpnext.svoenrav.queue_rules", ROOT / "erpnext/svoenrav/queue_rules.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class QueueRuleTests(unittest.TestCase):
	def test_manual_priority_wins_over_due_date_and_quantity(self):
		orders = [{"name": "SMALL", "qty": 1, "expected_delivery_date": "2026-11-01"}, {"name": "LARGE", "qty": 1000, "expected_delivery_date": "2026-12-01"}]
		plan = rules.normalise_queue([{"work_order": "LARGE", "priority": 1}, {"work_order": "SMALL", "priority": 2}])
		self.assertEqual([row["name"] for row in rules.sort_queue(orders, plan, "2026-11-04")], ["LARGE", "SMALL"])

	def test_ties_and_unranked_jobs_use_due_date_creation_and_name(self):
		orders = [{"name": "NO-DATE"}, {"name": "DUE", "expected_delivery_date": "2026-11-05"}, {"name": "FIRST", "expected_delivery_date": "2026-12-05"}]
		rows = rules.sort_queue(orders, {"FIRST": {"priority": 10}}, "2026-11-04")
		self.assertEqual([row["name"] for row in rows], ["FIRST", "DUE", "NO-DATE"])
		self.assertEqual(rules.sort_queue([{"name":"B"},{"name":"A"}], {}, "2026-11-04")[0]["name"], "A")

	def test_pauses_remain_in_place_and_do_not_change_native_status(self):
		order = {"name":"WO-1", "status":"In Process", "expected_delivery_date":"2026-11-03"}
		rows = rules.sort_queue([order], rules.normalise_queue([{"work_order":"WO-1","paused":1,"reason":"Нет кожи"}]), "2026-11-04")
		self.assertTrue(rows[0]["planning_paused"])
		self.assertTrue(rows[0]["overdue"])
		self.assertEqual(rows[0]["status"], "In Process")
		self.assertNotIn("planning_paused", order)

	def test_no_due_date_is_not_overdue(self):
		self.assertFalse(rules.sort_queue([{"name":"WO-1","status":"Stopped"}], {}, "2026-11-04")[0]["overdue"])
		self.assertTrue(rules.sort_queue([{"name":"WO-1","status":"Stopped"}], {}, "2026-11-04")[0]["native_stopped"])

	def test_invalid_priority_pause_or_duplicate_is_rejected(self):
		for extra in ({"priority":-1},{"priority":1.5},{"priority":True},{"priority":1000000},{"paused":1},{"paused":2},{"reason":"x"*501}):
			with self.subTest(extra=extra), self.assertRaises(ValueError):
				rules.normalise_queue([{"work_order":"WO-1",**extra}])
		with self.assertRaises(ValueError): rules.normalise_queue([{"work_order":"WO-1"},{"work_order":"WO-1"}])
		with self.assertRaises(ValueError): rules.normalise_queue([None])


def load_api(*, permitted=True, orders=None, planning=None):
	frappe = ModuleType("frappe")
	frappe.ValidationError = ValueError
	frappe.PermissionError = PermissionError
	frappe.throw = Mock(side_effect=lambda message, error=ValueError: (_ for _ in ()).throw(error(message)))
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.has_permission = Mock(side_effect=lambda doctype, ptype="read": permitted if doctype == "Work Order" else False)
	frappe.get_list = Mock(return_value=orders or [])
	children = [SimpleNamespace(as_dict=lambda row=row: row) for row in (planning or [])]
	frappe.get_single = Mock(return_value=SimpleNamespace(get=lambda field: children))
	utils = ModuleType("frappe.utils")
	utils.nowdate = lambda: "2026-11-04"
	utils.get_url_to_form = lambda doctype, name=None: "/desk/" + doctype.lower().replace(" ", "-") + (("/"+name) if name else "")
	portal = ModuleType("erpnext.svoenrav.portal")
	portal.require_staff = Mock()
	spec = importlib.util.spec_from_file_location("production_under_test", ROOT / "erpnext/svoenrav/production.py")
	api = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe":frappe, "frappe.utils":utils, "erpnext.svoenrav.portal":portal, "erpnext.svoenrav.queue_rules":rules}):
		spec.loader.exec_module(api)
	return api, frappe, portal


class QueueAPITests(unittest.TestCase):
	def test_source_permissions_are_required_before_settings_read(self):
		api, frappe, portal = load_api(permitted=False)
		with self.assertRaises(PermissionError): api.get_production_queue()
		frappe.get_single.assert_not_called()

	def test_guest_cannot_read_queue(self):
		api, frappe, portal = load_api()
		portal.require_staff.side_effect = PermissionError
		with self.assertRaises(PermissionError): api.get_production_queue()
		frappe.get_list.assert_not_called()

	def test_inaccessible_jobs_and_reasons_are_never_returned(self):
		api, frappe, portal = load_api(orders=[{"name":"VISIBLE","qty":1}], planning=[{"work_order":"SECRET","priority":1,"paused":1,"reason":"PRIVATE"},{"work_order":"VISIBLE","priority":2}])
		result = api.get_production_queue()
		self.assertEqual(result["rows"][0]["name"], "VISIBLE")
		self.assertNotIn("PRIVATE", str(result))
		self.assertNotIn("SECRET", str(result))
		self.assertNotIn("ignore_permissions", frappe.get_list.call_args.kwargs)

	def test_sorting_precedes_pagination(self):
		orders = [{"name":f"WO-{i:03}"} for i in range(60)]
		api, frappe, portal = load_api(orders=orders, planning=[{"work_order":"WO-059","priority":1}])
		first = api.get_production_queue()
		second = api.get_production_queue("50")
		self.assertEqual(first["rows"][0]["name"], "WO-059")
		self.assertEqual(len(first["rows"]), 50)
		self.assertTrue(first["has_more"])
		self.assertEqual(len(second["rows"]), 10)
		self.assertFalse(second["has_more"])

	def test_large_result_is_rejected_instead_of_showing_misleading_priorities(self):
		api, frappe, portal = load_api(orders=[{"name":str(i)} for i in range(1001)])
		with self.assertRaises(ValueError): api.get_production_queue()
		frappe.get_single.assert_not_called()

	def test_invalid_page_is_rejected(self):
		api, frappe, portal = load_api()
		for start in (-1, "x", True, 1001, 1.5):
			with self.subTest(start=start), self.assertRaises(ValueError): api.get_production_queue(start)
		frappe.get_list.assert_not_called()
