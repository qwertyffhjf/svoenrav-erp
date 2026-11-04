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
