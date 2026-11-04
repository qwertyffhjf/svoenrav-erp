import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from test_menu import menu
from test_queue import rules

ROOT = Path(__file__).resolve().parents[2]


class BaseDocument(SimpleNamespace):
	def get(self, field, default=None):
		return getattr(self, field, default)


def load_controller(stem):
	frappe = ModuleType("frappe")
	frappe.ValidationError = ValueError
	frappe.throw = Mock(side_effect=lambda message, error=ValueError: (_ for _ in ()).throw(error(message)))
	frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
	frappe.db = SimpleNamespace(exists=Mock(return_value=True))
	frappe.get_doc = Mock(return_value=SimpleNamespace(check_permission=Mock()))
	frappe.get_single = Mock()
	document = ModuleType("frappe.model.document")
	document.Document = BaseDocument
	portal = ModuleType("erpnext.svoenrav.portal")
	portal.require_staff = Mock()
	modules = {"frappe":frappe, "frappe.model.document":document, "erpnext.svoenrav.menu":menu, "erpnext.svoenrav.queue_rules":rules, "erpnext.svoenrav.portal":portal}
	context = patch.dict(sys.modules, modules)
	context.start()
	spec = importlib.util.spec_from_file_location(stem+"_controller", ROOT/f"erpnext/svoenrav/doctype/{stem}/{stem}.py")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module, frappe, portal, context


class SettingsTests(unittest.TestCase):
	def controller(self, stem="svoenrav_settings"):
		module, frappe, portal, context = load_controller(stem)
		self.addCleanup(context.stop)
		return module, frappe, portal

	def test_table_validation_does_not_change_legacy_json(self):
		module, frappe, portal = self.controller()
		doc = module.SVOENRAVSettings(brand_colour="#21372F", brand_name="SVOENRAV",description="",actions_json="old invalid JSON",menu_source="Таблица",menu_items=[])
		doc.validate()
		self.assertEqual(doc.actions_json,"old invalid JSON")

	def test_copy_requires_permission_on_settings(self):
		module, frappe, portal = self.controller()
		check = Mock(side_effect=PermissionError)
		frappe.get_single.return_value = SimpleNamespace(check_permission=check)
		with self.assertRaises(PermissionError): module.get_menu_editor_rows()
		check.assert_called_once_with("read")

	def test_copy_reads_settings_without_saving(self):
		module, frappe, portal = self.controller()
		settings = SimpleNamespace(check_permission=Mock(),actions_json="[]",menu_source="JSON",menu_items=[],save=Mock())
		frappe.get_single.return_value=settings
		self.assertEqual(module.get_menu_editor_rows(),[])
		settings.save.assert_not_called()
		portal.require_staff.assert_called_once()

	def test_guest_cannot_copy_settings(self):
		module, frappe, portal = self.controller()
		portal.require_staff.side_effect=PermissionError
		with self.assertRaises(PermissionError): module.get_menu_editor_rows()
		frappe.get_single.assert_not_called()

	def test_planning_settings_require_source_document_read(self):
		module, frappe, portal = self.controller("svoenrav_production_settings")
		row={"work_order":"WO-1","priority":1}
		doc=module.SVOENRAVProductionSettings(queue_items=[SimpleNamespace(as_dict=lambda:row)])
		doc.validate()
		frappe.get_doc.assert_called_once_with("Work Order","WO-1")
		frappe.get_doc.return_value.check_permission.assert_called_once_with("read")

	def test_duplicate_work_orders_cannot_be_saved(self):
		module, frappe, portal = self.controller("svoenrav_production_settings")
		row=SimpleNamespace(as_dict=lambda:{"work_order":"WO-1","priority":1})
		doc=module.SVOENRAVProductionSettings(queue_items=[row,row])
		with self.assertRaises(ValueError): doc.validate()
		frappe.get_doc.assert_not_called()
