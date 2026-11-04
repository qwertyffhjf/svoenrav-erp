import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("svoenrav_menu", ROOT / "erpnext/svoenrav/menu.py")
menu = importlib.util.module_from_spec(spec)
flow_spec = importlib.util.spec_from_file_location("erpnext.svoenrav.flow", ROOT / "erpnext/svoenrav/flow.py")
flow = importlib.util.module_from_spec(flow_spec)
flow_spec.loader.exec_module(flow)
with patch.dict(sys.modules, {"erpnext.svoenrav.flow": flow}):
	spec.loader.exec_module(menu)


class MenuTests(unittest.TestCase):
	def test_defaults_are_independent(self):
		first = menu.normalise_actions(None)
		first[0]["label"] = "Changed"
		self.assertEqual(menu.normalise_actions("")[0]["label"], "Новый заказ")
		first[2]["operation"] = "Changed"
		self.assertEqual(menu.normalise_actions(None)[2]["operation"], "transfer")

	def test_stock_entry_presets_and_sections(self):
		rows = [{"label": "Списание", "doctype": "Stock Entry", "mode": "new", "section": "quick", "defaults": {"stock_entry_type": "Material Issue"}}]
		self.assertEqual(menu.normalise_actions(json.dumps(rows))[0]["defaults"], rows[0]["defaults"])
		self.assertEqual(menu.normalise_actions(list(menu.DEFAULT_ACTIONS)), list(menu.DEFAULT_ACTIONS))

	def test_presets_cannot_set_amounts_statuses_or_arbitrary_fields(self):
		base = {"label": "X", "doctype": "Stock Entry", "mode": "new"}
		for extra in [
			{"defaults": {"stock_entry_type": "Material Issue", "docstatus": 1}},
			{"defaults": {"qty": 100}},
			{"defaults": {"stock_entry_type": "Manufacture"}},
			{"defaults": {"stock_entry_type": []}},
			{"defaults": []},
			{"defaults": {"stock_entry_type": "Material Issue"}, "mode": "list"},
			{"defaults": {"stock_entry_type": "Material Issue"}, "doctype": "Sales Order"},
			{"section": "<script>"},
			{"operation": "receipt"},
			{"operation": "transfer", "defaults": {"stock_entry_type": "Material Issue"}},
			{"operation": []},
		]:
			with self.subTest(extra=extra), self.assertRaises(ValueError):
				menu.normalise_actions([{**base, **extra}])

	def test_default_documents_and_presets_exist_in_this_checkout(self):
		documents = {}
		for path in (ROOT / "erpnext").glob("*/doctype/*/*.json"):
			data = json.loads(path.read_text())
			if isinstance(data, dict) and data.get("doctype") == "DocType":
				documents[data["name"]] = data
		for action in menu.DEFAULT_ACTIONS:
			with self.subTest(action=action["label"]):
				self.assertIn(action["doctype"], documents)
				for field in action.get("defaults", {}):
					self.assertIn(field, [row["fieldname"] for row in documents[action["doctype"]]["fields"]])

	def test_custom_document_and_empty_menu(self):
		rows = [{"label": "Моя форма", "doctype": "Свой документ", "mode": "new"}]
		self.assertEqual(menu.normalise_actions(json.dumps(rows))[0]["doctype"], "Свой документ")
		self.assertEqual(menu.normalise_actions("[]"), [])

	def test_invalid_actions_are_rejected(self):
		for raw in ["not json", {}, [None], [{"label": "X", "doctype": "javascript:alert(1)"}], [{"label": "X", "doctype": "Item", "url": "https://example.com"}], [{"label": "X", "doctype": "Item", "mode": "delete"}], [{"label": "", "doctype": "Item"}], [{"label": "X", "doctype": "Item"}] * 31]:
			with self.subTest(raw=raw), self.assertRaises(ValueError):
				menu.normalise_actions(raw)

	def test_colour_validation(self):
		self.assertEqual(menu.validate_colour("#a0B1c2"), "#a0B1c2")
		for value in ["red", "#fff", "#000000;background:url(x)", 123]:
			with self.subTest(value=value), self.assertRaises(ValueError):
				menu.validate_colour(value)


class MenuEditorTests(unittest.TestCase):
	def test_default_actions_roundtrip_through_table(self):
		actions = menu.normalise_actions(None)
		rows = menu.actions_to_rows(actions)
		self.assertEqual(menu.table_actions(rows), [{**action, "section": action.get("section", "modules")} for action in actions])

	def test_visibility_and_order_follow_table(self):
		rows = menu.actions_to_rows(menu.normalise_actions(None))[:3]
		rows[1]["enabled"] = 0
		rows.reverse()
		self.assertEqual([row["label"] for row in menu.table_actions(rows)], [rows[0]["label"], rows[2]["label"]])

	def test_explicit_table_source_does_not_fall_back_to_legacy_json(self):
		self.assertEqual(menu.resolve_actions("not JSON", "Таблица", []), [])
		rows = menu.actions_to_rows(menu.normalise_actions(None))[:1]
		self.assertEqual(menu.resolve_actions("[]", "Таблица", rows)[0]["label"], "Новый заказ")

	def test_legacy_source_ignores_unselected_table_and_preserves_empty_menu(self):
		self.assertEqual(menu.resolve_actions("[]", None, [None]), [])
		self.assertEqual(menu.resolve_actions(None, "JSON", []), menu.normalise_actions(None))
		with self.assertRaises(ValueError):
			menu.resolve_actions("[]", "unknown", [])

	def test_disabled_rows_cannot_store_arbitrary_operations(self):
		row = menu.actions_to_rows(menu.normalise_actions(None))[1]
		for extra in ({"enabled": 2}, {"guided_operation": "delete"}, {"action_doctype": "javascript:alert(1)"}, {"open_mode": "Удалить"}, {"menu_section": "unknown"}, {"guided_operation": ["Выпуск"]}):
			with self.subTest(extra=extra), self.assertRaises(ValueError):
				menu.table_actions([{**row, "enabled": 0, **extra}])

	def test_saved_json_presets_survive_table_conversion(self):
		actions = menu.normalise_actions([{"label": "Списание", "doctype": "Stock Entry", "mode": "new", "defaults": {"stock_entry_type": "Material Issue"}}])
		self.assertEqual(menu.table_actions(menu.actions_to_rows(actions))[0]["defaults"], actions[0]["defaults"])

	def test_editor_copy_keeps_disabled_rows_without_metadata(self):
		from types import SimpleNamespace
		rows = menu.actions_to_rows(menu.normalise_actions(None))[:2]
		rows[1].update({"enabled":0,"name":"private-child-name","owner":"private-owner"})
		settings = SimpleNamespace(menu_source="Таблица",menu_items=rows,actions_json="unchanged")
		result = menu.editor_rows(settings)
		self.assertEqual(len(result),2)
		self.assertEqual(result[1]["enabled"],0)
		self.assertNotIn("owner",result[1])
		self.assertEqual(settings.actions_json,"unchanged")
