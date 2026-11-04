import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("svoenrav_menu", ROOT / "erpnext/svoenrav/menu.py")
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class MenuTests(unittest.TestCase):
	def test_defaults_are_independent(self):
		first = menu.normalise_actions(None)
		first[0]["label"] = "Changed"
		self.assertEqual(menu.normalise_actions("")[0]["label"], "Принять материал")

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
