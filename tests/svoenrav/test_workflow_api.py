import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


def load(name, path=None):
	spec=importlib.util.spec_from_file_location(name,ROOT/(path or 'erpnext/svoenrav/'+name+'.py'))
	module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Doc(dict):
	def __init__(self, **values):
		super().__init__(values)
		object.__setattr__(self,'check_permission',Mock())
		object.__setattr__(self,'apply_fieldlevel_read_permissions',Mock())
	def __getattr__(self,key):
		if key in self:return self[key]
		raise AttributeError(key)
	def __setattr__(self,key,value):self[key]=value
	def as_dict(self):return dict(self)
	def is_new(self):return self.get('__islocal',True)


def source():
	return Doc(name='WO-1',company='C',docstatus=1,production_item='BAG',bom_no='BOM1',stock_uom='шт',qty=1,required_items=[{'item_code':'L','stock_uom':'дм²','required_qty':10}])


class WorkflowAPITests(unittest.TestCase):
	def setup(self):
		f=ModuleType('frappe');f.PermissionError=PermissionError;f.ValidationError=ValueError
		f.whitelist=lambda *a,**k:lambda fn:fn
		f.throw=Mock(side_effect=lambda message,error=ValueError:(_ for _ in ()).throw(error(message)))
		f.has_permission=Mock(return_value=True);f.get_list=Mock(return_value=[]);f.db=Mock();f.db.exists.return_value=False
		utils=ModuleType('frappe.utils');utils.get_url_to_form=lambda dt,name:'/desk/'+dt+'/'+name;utils.now=lambda:'NOW'
		portal=ModuleType('erpnext.svoenrav.portal');portal.require_staff=Mock()
		materials=ModuleType('erpnext.svoenrav.materials');materials.readable=Mock(return_value=source());materials.get_material_coverage=Mock(return_value={'status':'review','rows':[]})
		production=ModuleType('erpnext.svoenrav.production');production.get_production_queue=Mock(return_value={'total':1,'has_more':False,'rows':[{'name':'WO-1'}]})
		workshop=ModuleType('erpnext.svoenrav.workshop');workshop._source=Mock(return_value=source());workshop.get_order_card=Mock()
		modules={'frappe':f,'frappe.utils':utils,'erpnext.svoenrav.portal':portal,'erpnext.svoenrav.flow':load('flow'),'erpnext.svoenrav.spec_rules':load('spec_rules'),'erpnext.svoenrav.planning_rules':load('planning_rules'),'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.production':production,'erpnext.svoenrav.workshop':workshop}
		ctx=patch.dict(sys.modules,modules);ctx.start();self.addCleanup(ctx.stop)
		return f,portal,materials,production,workshop

	def test_queue_limit_blocks_partial_calculation_before_material_queries(self):
		f,p,m,q,w=self.setup();q.get_production_queue.return_value={'total':51,'has_more':True,'rows':[]}
		api=load('planning')
		with self.assertRaises(ValueError):api.get_queue_plan()
		m.readable.assert_not_called();m.get_material_coverage.assert_not_called()

	def test_hidden_order_information_does_not_turn_into_free_stock(self):
		f,p,m,q,w=self.setup();m.readable.side_effect=PermissionError
		api=load('planning');result=api.get_queue_plan()
		self.assertFalse(result['complete']);self.assertEqual(result['orders'][0]['status'],'unknown')

	def test_planning_guest_guard_prevents_queue_access(self):
		f,p,m,q,w=self.setup();p.require_staff.side_effect=PermissionError;api=load('planning')
		with self.assertRaises(PermissionError):api.get_queue_plan()
		q.get_production_queue.assert_not_called()

	def test_capture_checks_create_permission_before_insert(self):
		f,p,m,q,w=self.setup();f.has_permission.return_value=False;f.new_doc=Mock();api=load('specifications')
		with self.assertRaises(PermissionError):api.capture_specification('WO-1')
		f.new_doc.assert_not_called()

	def test_existing_hidden_snapshot_is_not_reported_as_missing(self):
		f,p,m,q,w=self.setup();f.db.exists.return_value=True;api=load('specifications')
		self.assertEqual(api.get_specification('WO-1')['state'],'unavailable')

	def test_missing_snapshot_does_not_fabricate_old_norms(self):
		f,p,m,q,w=self.setup();api=load('specifications');result=api.get_specification('WO-1')
		self.assertEqual(result['state'],'missing');self.assertNotIn('payload',result)

	def test_snapshot_controller_derives_payload_and_blocks_later_changes(self):
		f,p,m,q,w=self.setup();api=load('specifications')
		document=ModuleType('frappe.model.document');document.Document=Doc
		with patch.dict(sys.modules,{'erpnext.svoenrav.specifications':api,'frappe.model.document':document}):
			controller=load('snapshot_controller','erpnext/svoenrav/doctype/svoenrav_specification_snapshot/svoenrav_specification_snapshot.py')
			doc=controller.SVOENRAVSpecificationSnapshot(work_order='WO-1',company='EVIL',payload='FAKE',fingerprint='FAKE')
			doc.validate();self.assertEqual(doc.company,'C');self.assertEqual(json.loads(doc.payload)['bom_no'],'BOM1');self.assertEqual(len(doc.fingerprint),64)
			doc['__islocal']=False
			with self.assertRaises(ValueError):doc.validate()
			with self.assertRaises(ValueError):doc.on_trash()
			with self.assertRaises(ValueError):doc.before_rename()

	def test_snapshot_read_applies_field_permissions(self):
		f,p,m,q,w=self.setup();api=load('specifications');f.get_list.return_value=[{'name':'SNAP'}]
		m.readable.side_effect=[source(),Doc(name='SNAP',fingerprint=None,payload=None)]
		with self.assertRaises(PermissionError):api.get_specification('WO-1')

	def test_history_checks_order_before_version_access(self):
		f,p,m,q,w=self.setup();w._source.side_effect=PermissionError;api=load('history')
		with self.assertRaises(PermissionError):api.get_order_history('SECRET')
		f.get_list.assert_not_called();w.get_order_card.assert_not_called()

	def test_history_without_permission_returns_no_events(self):
		f,p,m,q,w=self.setup();f.has_permission.return_value=False;api=load('history')
		self.assertFalse(api.get_order_history('SO-1')['allowed']);f.get_list.assert_not_called()

	def test_history_only_exposes_allowlisted_readable_fields(self):
		f,p,m,q,w=self.setup();api=load('history')
		payload=json.dumps({'changed':[['status','Draft','Open'],['grand_total',100,200],['produced_qty',0,1],['docstatus',0,1]],'added':[{'SECRET':1}]})
		self.assertEqual(api.visible_changes(payload,{'status','grand_total','docstatus'}),[{'field':'status','before':'Draft','after':'Open'},{'field':'docstatus','before':0,'after':1}])
		for invalid in ('not json','[]','{"changed":null}'):
			self.assertEqual(api.visible_changes(invalid,{'status'}),[])

	def test_history_uses_exact_version_links_and_marks_truncation(self):
		f,p,m,q,w=self.setup();api=load('history')
		section={'allowed':True,'rows':[],'has_more':False}
		w.get_order_card.return_value={'order':{'name':'SO-1'},**{k:section for k in ('production','stock','deliveries','invoices','payments')}}
		w._source.return_value=Doc(name='SO-1',status='Open')
		f.get_list.return_value=[{'creation':'2026-11-04','data':json.dumps({'changed':[['status','Draft','Open']]})}]*21
		result=api.get_order_history('SO-1')
		self.assertEqual(len(result['rows']),20);self.assertTrue(result['partial'])
		self.assertEqual(f.get_list.call_args.kwargs['filters'],{'ref_doctype':'Sales Order','docname':'SO-1'})

	def test_capture_inserts_only_snapshot_with_normal_permissions(self):
		f,p,m,q,w=self.setup();api=load('specifications');doc=Doc();doc.insert=Mock()
		f.new_doc=Mock(return_value=doc);api.get_specification=Mock(return_value={'state':'matches'})
		result=api.capture_specification('WO-1')
		self.assertEqual(result['state'],'matches');self.assertEqual(doc.work_order,'WO-1')
		f.new_doc.assert_called_once_with('SVOENRAV Specification Snapshot');doc.insert.assert_called_once_with()
