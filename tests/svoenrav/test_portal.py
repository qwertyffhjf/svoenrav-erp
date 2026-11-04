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
	menu_spec.loader.exec_module(menu)
	portal_spec = importlib.util.spec_from_file_location("svoenrav_portal_under_test", ROOT / "erpnext/svoenrav/portal.py")
	portal = importlib.util.module_from_spec(portal_spec)
	with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils, "erpnext.svoenrav.menu": menu}):
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
