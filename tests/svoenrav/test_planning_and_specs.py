import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
	spec = importlib.util.spec_from_file_location(name, ROOT / ('erpnext/svoenrav/' + name + '.py'))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


plan = load('planning_rules')
specs = load('spec_rules')


def order(name='WO-1', **changes):
	return {'work_order':name, 'company':'C1', 'report':{'status':'unreserved', 'rows':[{'item_code':'LEATHER','item_name':'Кожа','stock_uom':'дм²','warehouse':'MAIN','status':'unreserved','actual':15,'reserved_total':5,'own_reserved':0,'free':10,'pending':8}]}, **changes}


def spec_order(**changes):
	return {'company':'C1','production_item':'BAG','bom_no':'BOM-1','stock_uom':'шт','qty':5,'required_items':[{'item_code':'LEATHER','stock_uom':'дм²','required_qty':50}], **changes}


class QueuePlanTests(unittest.TestCase):
	def test_free_stock_is_allocated_once_in_input_priority_order(self):
		result = plan.allocate([order('HIGH'), order('LOW')])
		self.assertTrue(result['complete'])
		self.assertEqual([o['rows'][0]['planned_free'] for o in result['orders']], [8,2])
		self.assertEqual(result['orders'][1]['rows'][0]['shortage'],6)

	def test_own_reserves_are_not_pooled(self):
		a,b=order('A'),order('B');a['report']['rows'][0]['own_reserved']=5
		result=plan.allocate([a,b])
		self.assertEqual([o['rows'][0]['planned_free'] for o in result['orders']],[3,7])

	def test_paused_orders_do_not_take_stock(self):
		result=plan.allocate([order('A',paused=True),order('B')])
		self.assertEqual(result['orders'][0]['status'],'paused')
		self.assertEqual(result['orders'][1]['rows'][0]['planned_free'],8)

	def test_company_and_warehouse_are_separate_pools(self):
		for kind in ('company','warehouse'):
			a,b=order('A'),order('B')
			if kind=='company':b['company']='C2'
			else:b['report']['rows'][0]['warehouse']='OTHER'
			self.assertEqual([o['rows'][0]['planned_free'] for o in plan.allocate([a,b])['orders']],[8,8])

	def test_any_unknown_active_demand_blocks_all_assignments(self):
		for invalid in (None, {'status':'review','rows':[]}, {'status':'review','rows':[{'item_code':'HIDDEN'}]}):
			result=plan.allocate([order('A',report=invalid),order('B')])
			self.assertFalse(result['complete'])
			self.assertIsNone(result['orders'][1]['rows'][0]['planned_free'])

	def test_changed_balances_use_conservative_minimum(self):
		a,b=order('A'),order('B');b['report']['rows'][0].update(actual=10,free=5)
		result=plan.allocate([a,b]);self.assertEqual(result['orders'][0]['rows'][0]['planned_free'],5)
		self.assertEqual(result['orders'][1]['rows'][0]['planned_free'],0)

	def test_conflicting_units_and_overlapping_reserves_block_plan(self):
		for case in ('uom','reserve'):
			a,b=order('A'),order('B')
			if case=='uom':b['report']['rows'][0]['stock_uom']='м²'
			else:
				a['report']['rows'][0]['own_reserved']=4;b['report']['rows'][0]['own_reserved']=4
			self.assertFalse(plan.allocate([a,b])['complete'])

	def test_invalid_quantities_never_become_zero(self):
		for invalid in (None,True,-1,'NaN','Infinity'):
			a=order();a['report']['rows'][0]['free']=invalid
			self.assertFalse(plan.allocate([a])['complete'])

	def test_allocation_does_not_mutate_reports(self):
		a=order();before=json.dumps(a,sort_keys=True);plan.allocate([a]);self.assertEqual(json.dumps(a,sort_keys=True),before)

	def test_decimal_allocation_has_no_binary_float_residue(self):
		a,b=order('A'),order('B')
		for entry in (a,b):entry['report']['rows'][0].update(actual='0.3',reserved_total=0,own_reserved=0,free='0.3',pending='0.2')
		result=plan.allocate([a,b])
		self.assertEqual(result['orders'][1]['rows'][0]['planned_free'],0.1)
		self.assertEqual(result['orders'][1]['rows'][0]['shortage'],0.1)


class SpecificationTests(unittest.TestCase):
	def test_progress_and_bom_later_edits_do_not_change_fingerprint(self):
		base=spec_order();changed=spec_order(produced_qty=3,status='Completed')
		changed['required_items'][0]['transferred_qty']=30
		self.assertEqual(specs.specification(base),specs.specification(changed))

	def test_material_qty_uom_bom_and_product_changes_are_detected(self):
		base=specs.specification(spec_order())[1]
		for change in ({'qty':6},{'bom_no':'BOM-2'},{'production_item':'BAG2'},{'required_items':[{'item_code':'L2','stock_uom':'дм²','required_qty':50}]},{'required_items':[{'item_code':'LEATHER','stock_uom':'м²','required_qty':50}]}):
			self.assertNotEqual(base,specs.specification(spec_order(**change))[1])

	def test_equivalent_number_and_row_order_have_stable_digest(self):
		a=spec_order(qty='5.000');b=spec_order(qty=5)
		a['required_items'].append({'item_code':'ZIP','stock_uom':'шт','required_qty':5})
		b['required_items'].insert(0,{'item_code':'ZIP','stock_uom':'шт','required_qty':'5.0'})
		self.assertEqual(specs.specification(a),specs.specification(b))

	def test_missing_fields_and_invalid_numbers_fail_closed(self):
		for change in ({'company':None},{'required_items':[]},{'qty':'NaN'},{'qty':True},{'qty':-1}):
			with self.assertRaises(ValueError):specs.specification(spec_order(**change))

	def test_native_snapshot_schema_disallows_edit_delete_and_duplicate_order(self):
		schema=json.loads((ROOT/'erpnext/svoenrav/doctype/svoenrav_specification_snapshot/svoenrav_specification_snapshot.json').read_text())
		self.assertTrue(next(f for f in schema['fields'] if f['fieldname']=='work_order')['unique'])
		for permission in schema['permissions']:
			self.assertFalse(permission.get('write'));self.assertFalse(permission.get('delete'))
