import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class Redirect(Exception):
	pass


def load_portal(*, user="master", user_type="System User", permissions=None, actions=""):
	permissions = permissions or {}
	frappe = ModuleType("frappe")
	frappe.session = SimpleNamespace(user=user)
	frappe.PermissionError = PermissionError
	frappe.ValidationError = ValueError
	frappe.redirect = Mock(side_effect=Redirect)
	frappe.throw = Mock(side_effect=lambda message, error=ValueError: (_ for _ in ()).throw(error(message)))
	frappe.get_cached_value = Mock(return_value=user_type)
	frappe.get_single = Mock(return_value=SimpleNamespace(actions_json=actions, brand_colour="#21372F", brand_name="SVOENRAV", description="Мастерская"))
	frappe.db = SimpleNamespace(exists=Mock(return_value=True))
	frappe.has_permission = Mock(side_effect=lambda doctype, ptype="read": permissions.get((doctype, ptype), False))
	frappe.get_meta = Mock(return_value=SimpleNamespace(issingle=False))
	frappe.scrub = lambda value: value.lower().replace(" ", "_")
	frappe.get_list = Mock(return_value=[])
	frappe.get_roles = Mock(return_value=[])
	utils = ModuleType("frappe.utils")
	utils.get_url_to_form = lambda doctype, name=None: "/desk/" + doctype.lower().replace(" ", "-") + (("/" + name) if name else "")
	utils.get_url_to_list = lambda doctype: utils.get_url_to_form(doctype)
	menu_spec = importlib.util.spec_from_file_location("erpnext.svoenrav.menu", ROOT / "erpnext/svoenrav/menu.py")
	menu = importlib.util.module_from_spec(menu_spec)
	flow_spec = importlib.util.spec_from_file_location("erpnext.svoenrav.flow", ROOT / "erpnext/svoenrav/flow.py")
	flow = importlib.util.module_from_spec(flow_spec)
	flow_spec.loader.exec_module(flow)
	with patch.dict(sys.modules, {"erpnext.svoenrav.flow": flow}):
		menu_spec.loader.exec_module(menu)
	portal_spec = importlib.util.spec_from_file_location("svoenrav_portal_under_test", ROOT / "erpnext/svoenrav/portal.py")
	portal = importlib.util.module_from_spec(portal_spec)
	with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils, "erpnext.svoenrav.menu": menu, "erpnext.svoenrav.flow": flow}):
		portal_spec.loader.exec_module(portal)
	return portal, frappe


class PortalPermissionTests(unittest.TestCase):
	def test_guest_cannot_read_settings_or_jobs(self):
		portal, frappe = load_portal(user="Guest")
		with self.assertRaises(Redirect):
			portal.get_page_context()
		frappe.get_single.assert_not_called()
		frappe.get_list.assert_not_called()

	def test_customer_portal_user_is_rejected(self):
		portal, frappe = load_portal(user_type="Website User")
		with self.assertRaises(PermissionError):
			portal.get_page_context()
		frappe.get_single.assert_not_called()

	def test_create_permission_is_required_for_receipt(self):
		portal, frappe = load_portal(permissions={("Purchase Receipt", "read"): True, ("Item", "read"): True})
		context = portal.get_page_context()
		self.assertEqual([row["doctype"] for row in context["actions"]], ["Item"])
		frappe.get_list.assert_not_called()
		self.assertFalse(context["can_configure"])
		self.assertEqual(context["quick_actions"], [])
		self.assertFalse(context["can_read_work_orders"])

	def test_quick_actions_use_create_permission_and_safe_presets(self):
		portal, frappe = load_portal(permissions={("Stock Entry", "create"): True, ("Stock Entry Type", "read"): True}, actions='[ {"label":"Списать материалы","doctype":"Stock Entry","mode":"new","section":"quick","defaults":{"stock_entry_type":"Material Issue"}} ]')
		frappe.get_list.return_value = [{"name": "Списание материалов"}]
		context = portal.get_page_context()
		self.assertEqual([row["label"] for row in context["quick_actions"]], ["Списать материалы"])
		from urllib.parse import parse_qs, urlsplit
		self.assertEqual(parse_qs(urlsplit(context["quick_actions"][0]["url"]).query), {"stock_entry_type": ["Списание материалов"]})
		self.assertEqual(context["module_actions"], [])
		self.assertEqual(frappe.get_list.call_args.kwargs["filters"], {"purpose": "Material Issue", "is_standard": 1})
		self.assertNotIn("ignore_permissions", frappe.get_list.call_args.kwargs)

	def test_unavailable_stock_type_cannot_open_wrong_operation(self):
		for can_read in (True, False):
			with self.subTest(can_read=can_read):
				portal, frappe = load_portal(permissions={("Stock Entry", "create"): True, ("Stock Entry Type", "read"): can_read}, actions='[ {"label":"Списать материалы","doctype":"Stock Entry","mode":"new","section":"quick","defaults":{"stock_entry_type":"Material Issue"}} ]')
				context = portal.get_page_context()
				self.assertEqual(context["quick_actions"], [])
				self.assertEqual(len(context["action_warnings"]), 1)
				if not can_read:
					frappe.get_list.assert_not_called()

	def test_saved_legacy_menu_stays_in_modules_without_new_defaults(self):
		portal, frappe = load_portal(permissions={("Item", "read"): True}, actions='[{"label":"Мои материалы","doctype":"Item"}]')
		context = portal.get_page_context()
		self.assertEqual(context["quick_actions"], [])
		self.assertEqual([row["label"] for row in context["module_actions"]], ["Мои материалы"])

	def test_guided_actions_require_source_read_and_target_create(self):
		portal, frappe = load_portal(permissions={("Stock Entry", "create"): True})
		self.assertEqual(portal.get_page_context()["quick_actions"], [])
		portal, frappe = load_portal(permissions={("Stock Entry", "create"): True, ("Work Order", "read"): True})
		context = portal.get_page_context()
		self.assertEqual([row["operation"] for row in context["quick_actions"]], ["transfer", "manufacture"])
		self.assertEqual(context["quick_actions"][1]["url"], "/desk/svoenrav-workshop?operation=manufacture")

	def test_explicit_empty_menu_does_not_restore_default_actions(self):
		portal, frappe = load_portal(actions="[]")
		context = portal.get_page_context()
		self.assertEqual(context["actions"], [])

	def test_missing_document_is_hidden_even_with_permission(self):
		portal, frappe = load_portal(permissions={("Item", "read"): True})
		frappe.db.exists.return_value = False
		self.assertEqual(portal.get_page_context()["actions"], [])

	def test_allowed_work_orders_use_permission_aware_list(self):
		portal, frappe = load_portal(permissions={("Work Order", "read"): True})
		frappe.get_list.return_value = [{"name": "WO-1", "item_name": "Сумка", "qty": 2, "produced_qty": 1}]
		context = portal.get_page_context()
		self.assertEqual(context["work_orders"][0]["url"], "/desk/work-order/WO-1")
		self.assertNotIn("ignore_permissions", frappe.get_list.call_args.kwargs)

	def test_invalid_saved_menu_fails_visibly(self):
		portal, frappe = load_portal(actions="invalid json")
		with self.assertRaises(ValueError):
			portal.get_page_context()
		frappe.get_list.assert_not_called()
