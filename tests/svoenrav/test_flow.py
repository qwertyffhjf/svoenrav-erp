import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("svoenrav_flow_under_test", ROOT / "erpnext/svoenrav/flow.py")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)


def order(**extra):
	return {"docstatus": 1, "status": "In Process", "qty": 10, "produced_qty": 2, "material_transferred_for_manufacturing": 6, **extra}


class ProductionFlowTests(unittest.TestCase):
	def test_partial_transfer_and_release_have_different_limits(self):
		self.assertEqual(flow.validate_production("transfer", order(), "4"), Decimal(4))
		self.assertEqual(flow.validate_production("manufacture", order(), "4"), Decimal(4))
		with self.assertRaises(ValueError):
			flow.validate_production("manufacture", order(), "5")
		with self.assertRaises(ValueError):
			flow.validate_production("transfer", order(), "5")

	def test_release_cannot_exceed_plan_even_if_overtransferred(self):
		with self.assertRaises(ValueError):
			flow.validate_production("manufacture", order(material_transferred_for_manufacturing=15), 9)

	def test_no_transfer_scenario_only_allows_release(self):
		self.assertEqual(flow.validate_production("manufacture", order(skip_transfer=1), 8), Decimal(8))
		with self.assertRaises(ValueError):
			flow.validate_production("transfer", order(skip_transfer=1), 1)

	def test_finished_stopped_or_draft_work_orders_are_rejected(self):
		for changes in ({"docstatus": 0}, {"docstatus": 2}, {"status": "Stopped"}, {"status": "Closed"}, {"status": "Completed"}):
			with self.subTest(changes=changes), self.assertRaises(ValueError):
				flow.validate_production("manufacture", order(**changes), 1)

	def test_separate_consumption_cannot_use_shortcut(self):
		for operation in ("transfer", "manufacture"):
			with self.subTest(operation=operation), self.assertRaises(ValueError):
				flow.validate_production(operation, order(), 1, separate_consumption=True)

	def test_advanced_scenarios_use_full_native_work_order(self):
		for changes in ({"track_semi_finished_goods": 1}, {"transfer_material_against": "Job Card"}, {"process_loss_qty": 1}, {"operations": [{"process_loss_qty": 1}]}, {"subcontracting_inward_order": "SIO-1"}, {"disassembled_qty": 1}):
			with self.subTest(changes=changes), self.assertRaises(ValueError):
				flow.validate_production("manufacture", order(**changes), 1)

	def test_invalid_quantities_do_not_reach_native_factory(self):
		for quantity in (None, "", "abc", True, False, "NaN", "Infinity", "-Infinity", 0, -1, "1e-999"):
			with self.subTest(quantity=quantity), self.assertRaises(ValueError):
				flow.validate_production("manufacture", order(), quantity)

	def test_fractional_quantities_are_preserved(self):
		self.assertEqual(flow.validate_production("manufacture", order(), "1.25"), Decimal("1.25"))

	def test_source_name_is_validated(self):
		self.assertEqual(flow.validate_source(" SO-1 "), "SO-1")
		for value in (None, {}, "", " ", "x" * 141, "a\x00b"):
			with self.subTest(value=value), self.assertRaises(ValueError):
				flow.validate_source(value)
