import importlib.util
import sys
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


def load(name):
	spec=importlib.util.spec_from_file_location(name,ROOT/f'erpnext/svoenrav/{name}.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Doc(dict):
	def __getattr__(self,key):return self.get(key)
	def __setattr__(self,key,value):self[key]=value
	def as_dict(self):return dict(self)
	def is_new(self):return self.get('__islocal',True)


class Expression:
	def __init__(self,fn):self.fn=fn
	def __and__(self,other):return Expression(lambda row:self.fn(row) and other.fn(row))


class Field:
	def __init__(self,key):self.key=key
	def __eq__(self,value):return Expression(lambda row:row.get(self.key)==value)
	def __ne__(self,value):return Expression(lambda row:row.get(self.key)!=value)


class Table:
	def __getattr__(self,key):return Field(key)
	def __getitem__(self,key):return Field(key)


class Query:
	def __init__(self,rows):self.rows=rows;self.condition=None;self.locking=False
	def select(self,*args):return self
	def where(self,condition):self.condition=condition if self.condition is None else self.condition & condition;return self
	def limit(self,*args):return self
	def orderby(self,*args,**kwargs):return self
	def for_update(self):self.locking=True;return self
	def run(self,**kwargs):
		if not self.locking:raise AssertionError('Concurrency guard must use a current/locking read')
		return [row for row in self.rows if self.condition.fn(row)]


def frappe_stub():
	f=ModuleType('frappe');f.ValidationError=ValueError;f.PermissionError=PermissionError;f.DoesNotExistError=LookupError
	f.throw=lambda message,error=ValueError:(_ for _ in ()).throw(error(message))
	f.whitelist=lambda *a,**k:lambda fn:fn;f.db=Mock();return f


money=load('payment_rules')


class PaymentShareTests(unittest.TestCase):
	def test_direct_and_single_order_invoice_are_exact(self):
		self.assertEqual(money.reference_share({'reference_doctype':'Sales Order','reference_name':'SO','allocated_amount':100},'SO',set(),{})[0],100)
		self.assertEqual(money.reference_share({'reference_doctype':'Sales Invoice','allocated_amount':100},'SO',{'SO'},{}),(money.money(100),'invoice'))

	def test_mixed_invoice_requires_explicit_share_never_proportions(self):
		ref={'reference_doctype':'Sales Invoice','allocated_amount':100}
		self.assertEqual(money.reference_share(ref,'SO',{'SO','OTHER'},{}),(None,'needs_split'))
		self.assertEqual(money.reference_share(ref,'SO',{'SO','OTHER'},{'SO':30,'OTHER':70}),(money.money(30),'explicit'))
		self.assertEqual(money.reference_share(ref,'SO',{'SO',''},{}),(None,'needs_split'))

	def test_total_and_sign_are_checked_with_exact_decimals(self):
		self.assertEqual(money.validate_split('0.3','0.1',['0.2']),money.money('0.1'))
		for value,others in [(101,[]),(50,[51]),(-1,[]),(20,[-1]),('NaN',[])]:
			with self.assertRaises(ValueError):money.validate_split(100,value,others)
		self.assertEqual(money.validate_split(-100,-30,[-70]),-30)


class ConcurrentDraftTests(unittest.TestCase):
	def test_two_simultaneous_saves_only_one_pending_operation(self):
		f=frappe_stub();rows=[];parent_lock=threading.Lock();start=threading.Barrier(2)
		f.db.get_value.side_effect=lambda *args,**kw: (parent_lock.acquire() or True)
		f.qb=SimpleNamespace(DocType=lambda name:Table(),from_=lambda table:Query(rows))
		with patch.dict(sys.modules,{'frappe':f}):api=load('transactions')
		def save(name):
			start.wait()
			try:
				api.guard_duplicate_draft(Doc(doctype='Stock Entry',name=name,docstatus=0,work_order='WO',purpose='Manufacture'))
				rows.append({'name':name,'docstatus':0,'work_order':'WO','purpose':'Manufacture'})
				return 'saved'
			except ValueError:return 'blocked'
			finally:parent_lock.release()
		with ThreadPoolExecutor(2) as pool:
			results=list(pool.map(save,['A','B']))
		self.assertCountEqual(results,['saved','blocked']);self.assertEqual(len(rows),1)
		self.assertTrue(all(call.kwargs.get('for_update') for call in f.db.get_value.call_args_list))

	def test_receipt_sources_are_sorted_and_returns_do_not_block_normal_receipt(self):
		f=frappe_stub()
		with patch.dict(sys.modules,{'frappe':f}):api=load('transactions')
		doc=Doc(doctype='Purchase Receipt',items=[Doc(purchase_order='B'),Doc(purchase_order='A'),Doc(purchase_order='B')])
		self.assertEqual(api.draft_sources(doc),[('Purchase Order','A'),('Purchase Order','B')])
		doc.is_return=1;self.assertEqual(api.draft_sources(doc),[])

	def test_current_document_and_other_purposes_do_not_conflict(self):
		f=frappe_stub();rows=[{'name':'SELF','docstatus':0,'work_order':'WO','purpose':'Manufacture'},{'name':'TRANSFER','docstatus':0,'work_order':'WO','purpose':'Material Transfer for Manufacture'}]
		f.qb=SimpleNamespace(DocType=lambda name:Table(),from_=lambda table:Query(rows))
		with patch.dict(sys.modules,{'frappe':f}):api=load('transactions')
		api.guard_duplicate_draft(Doc(doctype='Stock Entry',name='SELF',docstatus=0,work_order='WO',purpose='Manufacture'))


class EventAndAccessTests(unittest.TestCase):
	def test_hook_permission_signatures_use_native_ptype_and_cannot_grant_create(self):
		f=frappe_stub();f.has_permission=Mock(return_value=True)
		source=Doc(doctype='Work Order',status='In Process');source.apply_fieldlevel_read_permissions=Mock()
		f.get_doc=Mock(return_value=source)
		with patch.dict(sys.modules,{'frappe':f}):events=load('events')
		with patch.dict(sys.modules,{'frappe':f,'erpnext.svoenrav.events':events,'erpnext.svoenrav.flow':load('flow')}):access=load('access')
		doc=Doc(reference_doctype='Work Order',reference_name='WO',payload='{"status":"In Process"}',before_payload='{}')
		self.assertTrue(access.event_permission(doc,ptype='read'));self.assertFalse(access.event_permission(doc,ptype='create'))
		doc.payload='{"outstanding_amount":100}'
		self.assertFalse(access.event_permission(doc,ptype='read'))
		self.assertEqual(access.event_query(), '1=0')

	def test_event_cannot_be_forged_edited_or_deleted(self):
		f=frappe_stub();document=ModuleType('frappe.model.document');document.Document=Doc
		with patch.dict(sys.modules,{'frappe':f,'frappe.model.document':document}):
			events=load('events')
			with patch.dict(sys.modules,{'erpnext.svoenrav.events':events}):
				path=ROOT/'erpnext/svoenrav/doctype/svoenrav_operation_event/svoenrav_operation_event.py';spec=importlib.util.spec_from_file_location('event_controller',path);controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
				doc=controller.SVOENRAVOperationEvent()
				with self.assertRaises(PermissionError):doc.validate()
				token=events.INTERNAL.set(True)
				try:doc.validate();doc['__islocal']=False;self.assertRaises(PermissionError,doc.validate)
				finally:events.INTERNAL.reset(token)
				with self.assertRaises(PermissionError):doc.on_trash()

	def test_role_defaults_do_not_grant_operator_submit_or_finance(self):
		f=frappe_stub()
		with patch.dict(sys.modules,{'frappe':f}):roles=load('roles')
		operator=roles.PROFILES['SVOENRAV Operator']
		self.assertNotIn('submit',operator['Stock Entry']);self.assertNotIn('Payment Entry',operator)
		self.assertIn('submit',roles.PROFILES['SVOENRAV Owner']['Work Order'])
		self.assertIn('submit',roles.PROFILES['SVOENRAV Planner']['Stock Reservation Entry'])


class NativeReservationAPITests(unittest.TestCase):
	def setup(self):
		f=frappe_stub();f.has_permission=Mock(return_value=True);f.new_doc=Mock()
		portal=ModuleType('erpnext.svoenrav.portal');portal.require_staff=Mock()
		production=ModuleType('erpnext.svoenrav.production');production.get_production_queue=Mock(return_value={'total':1,'has_more':False,'rows':[{'name':'WO'}]})
		planning=ModuleType('erpnext.svoenrav.planning');planning.get_queue_plan=Mock(return_value={'complete':True,'orders':[{'work_order':'WO','status':'covered','rows':[{'item_code':'L','warehouse':'WH','stock_uom':'дм²','planned_free':2}]}]})
		materials=ModuleType('erpnext.svoenrav.materials')
		order=Doc(name='WO',doctype='Work Order',company='C',docstatus=1,status='In Process',skip_transfer=0,required_items=[Doc(name='ROW',item_code='L',required_qty=10,transferred_qty=4,stock_reserved_qty=4,source_warehouse='WH')]);order.check_permission=Mock()
		materials.readable=Mock(return_value=order)
		transactions=ModuleType('erpnext.svoenrav.transactions');transactions.lock=Mock()
		utils=ModuleType('frappe.utils');utils.get_url_to_form=lambda dt,name:'/desk/'+name
		modules={'frappe':f,'frappe.utils':utils,'erpnext.svoenrav.portal':portal,'erpnext.svoenrav.production':production,'erpnext.svoenrav.planning':planning,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.transactions':transactions,'erpnext.svoenrav.material_rules':load('material_rules')}
		context=patch.dict(sys.modules,modules);context.start();self.addCleanup(context.stop)
		doc=Doc(doctype='Stock Reservation Entry',name='SRE');doc.insert=Mock();doc.submit=Mock();f.new_doc.return_value=doc
		return load('reservations'),f,portal,production,planning,order,doc

	def test_native_reservation_is_created_with_exact_detail_and_without_permission_bypass(self):
		api,f,p,q,plan,order,doc=self.setup();result=api.reserve_queue()
		self.assertEqual(result['count'],1);self.assertEqual(doc.reserved_qty,2);self.assertEqual(doc.voucher_detail_no,'ROW')
		doc.insert.assert_called_once_with();doc.submit.assert_called_once_with();order.check_permission.assert_called_with('write');f.db.commit.assert_not_called()

	def test_missing_submit_right_stops_before_reading_queue(self):
		api,f,p,q,plan,order,doc=self.setup();f.has_permission.side_effect=lambda dt,ptype:ptype!='submit'
		with self.assertRaises(PermissionError):api.reserve_queue()
		q.get_production_queue.assert_not_called();doc.insert.assert_not_called()

	def test_incomplete_plan_and_changed_queue_never_create_reservations(self):
		for value in ({'complete':False},{'complete':True,'orders':[{'work_order':'NEW','status':'covered'}]}):
			api,f,p,q,plan,order,doc=self.setup();plan.get_queue_plan.return_value=value
			with self.assertRaises(ValueError):api.reserve_queue()
			doc.insert.assert_not_called();f.db.commit.assert_not_called()

	def test_native_error_is_propagated_for_transaction_rollback(self):
		api,f,p,q,plan,order,doc=self.setup();doc.submit.side_effect=ValueError('Native stock error')
		with self.assertRaises(ValueError):api.reserve_queue()
		f.db.commit.assert_not_called()

	def test_repeated_fully_reserved_plan_does_not_create_another_entry(self):
		api,f,p,q,plan,order,doc=self.setup();plan.get_queue_plan.return_value['orders'][0]['rows'][0]['planned_free']=0
		self.assertEqual(api.reserve_queue()['count'],0);doc.insert.assert_not_called()


class AutomaticSnapshotTests(unittest.TestCase):
	def test_work_order_submit_captures_once_and_propagates_failure(self):
		f=frappe_stub();f.db.exists.return_value=False;doc=Doc();doc.insert=Mock();f.new_doc=Mock(return_value=doc)
		utils=ModuleType('frappe.utils');utils.get_url_to_form=Mock()
		materials=ModuleType('erpnext.svoenrav.materials');materials.readable=Mock()
		portal=ModuleType('erpnext.svoenrav.portal');portal.require_staff=Mock()
		with patch.dict(sys.modules,{'frappe':f,'frappe.utils':utils,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.portal':portal,'erpnext.svoenrav.spec_rules':load('spec_rules'),'erpnext.svoenrav.flow':load('flow')}):api=load('specifications')
		api.capture_on_submit(Doc(name='WO'));self.assertEqual(doc.work_order,'WO');doc.insert.assert_called_once_with()
		f.db.exists.return_value=True;api.capture_on_submit(Doc(name='WO'));self.assertEqual(doc.insert.call_count,1)
		f.db.exists.return_value=False;doc.insert.side_effect=ValueError('Invalid BOM')
		with self.assertRaises(ValueError):api.capture_on_submit(Doc(name='WO'))

	def test_pack_freezes_nested_bom_routes_and_detects_cycles(self):
		f=frappe_stub();f.has_permission=Mock(return_value=False)
		boms={'A':Doc(docstatus=1,name='A',item='BAG',quantity=1,modified='DATE',items=[Doc(item_code='SUB',qty=2,bom_no='B')]),'B':Doc(docstatus=1,name='B',item='SUB',quantity=1,modified='DATE',items=[Doc(item_code='L',qty=3)])}
		materials=ModuleType('erpnext.svoenrav.materials');materials.readable=lambda dt,name:boms[name]
		with patch.dict(sys.modules,{'frappe':f,'erpnext.svoenrav.materials':materials}):api=load('spec_pack')
		payload,digest=api.build_pack(Doc(name='WO',bom_no='A',operations=[Doc(operation='CUT',time_in_mins=5)]))
		import json
		self.assertEqual(set(json.loads(payload)['boms']),{'A','B'});self.assertEqual(len(digest),64)
		boms['B']['items'][0]['qty']=6;self.assertNotEqual(digest,api.build_pack(Doc(name='WO',bom_no='A'))[1])
		boms['B']['items'][0]['bom_no']='A'
		with self.assertRaises(ValueError):api.build_pack(Doc(name='WO',bom_no='A'))


class PaymentAdapterTests(unittest.TestCase):
	def test_native_signed_refund_is_not_inverted_and_currencies_are_separate(self):
		f=frappe_stub();f.has_permission=Mock(return_value=True)
		payments={'PAY':Doc(name='PAY',docstatus=1,party_type='Customer',payment_type='Pay',paid_to_account_currency='RUB',references=[Doc(name='R1',reference_doctype='Sales Order',reference_name='SO',allocated_amount=-20)]),'RECEIVE':Doc(name='RECEIVE',docstatus=1,party_type='Customer',payment_type='Receive',paid_from_account_currency='USD',references=[Doc(name='R2',reference_doctype='Sales Order',reference_name='SO',allocated_amount=100)])}
		materials=ModuleType('erpnext.svoenrav.materials');materials.readable=lambda dt,name:payments[name]
		with patch.dict(sys.modules,{'frappe':f,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.payment_rules':money}):api=load('payments')
		result=api.enrich_payments({'allowed':True,'has_more':False,'rows':[{'name':'PAY'},{'name':'RECEIVE'}]},'SO')
		self.assertEqual(result['order_totals'],{'RUB':-20,'USD':100});self.assertEqual(result['rows'][0]['order_amount'],-20)

	def test_unknown_mixed_invoice_does_not_produce_a_zero_or_partial_total(self):
		f=frappe_stub();f.has_permission=Mock(return_value=True);f.get_list=Mock(return_value=[])
		f.qb=Mock();f.qb.from_.return_value.select.return_value.where.return_value.limit.return_value.run.return_value=[]
		payment=Doc(name='PAY',docstatus=1,party_type='Customer',payment_type='Receive',paid_from_account_currency='RUB',references=[Doc(name='REF',reference_doctype='Sales Invoice',reference_name='INV',allocated_amount=100)])
		invoice=Doc(items=[Doc(sales_order='SO'),Doc(sales_order='OTHER')])
		materials=ModuleType('erpnext.svoenrav.materials');materials.readable=lambda dt,name:payment if dt=='Payment Entry' else invoice
		with patch.dict(sys.modules,{'frappe':f,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.payment_rules':money}):api=load('payments')
		result=api.enrich_payments({'allowed':True,'has_more':False,'rows':[{'name':'PAY'}]},'SO')
		self.assertIsNone(result['order_totals']);self.assertIsNone(result['rows'][0]['order_amount']);self.assertEqual(result['rows'][0]['allocation_state'],'needs_split')


class FrozenNormsTests(unittest.TestCase):
	def test_progress_is_allowed_but_native_norm_edits_are_blocked(self):
		f=frappe_stub();rules=load('spec_rules');doc=Doc(name='WO',company='C',production_item='BAG',bom_no='BOM',stock_uom='шт',qty=1,required_items=[Doc(item_code='L',required_qty=10,stock_uom='дм²')]);f.db.get_value.return_value=rules.specification(doc)[1]
		utils=ModuleType('frappe.utils');utils.get_url_to_form=Mock();materials=ModuleType('erpnext.svoenrav.materials');materials.readable=Mock();portal=ModuleType('erpnext.svoenrav.portal');portal.require_staff=Mock()
		with patch.dict(sys.modules,{'frappe':f,'frappe.utils':utils,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.portal':portal,'erpnext.svoenrav.spec_rules':rules,'erpnext.svoenrav.flow':load('flow')}):api=load('specifications')
		doc.produced_qty=1;doc.required_items[0]['consumed_qty']=10;api.guard_frozen_norms(doc)
		doc.required_items[0]['required_qty']=11
		with self.assertRaises(ValueError):api.guard_frozen_norms(doc)


class VisibilityRegressionTests(unittest.TestCase):
	def test_frappe_synthetic_zeroes_and_masked_fields_are_not_readable_fields(self):
		flow=load('flow')
		class Native:
			def __init__(self):self.qty=2;self.masked=0;self.flags={'masked_fieldnames':{'masked'}}
			def as_dict(self):return {'qty':2,'missing_numeric':0,'masked':0}
		self.assertEqual(flow.visible_dict(Native()),{'qty':2})

	def test_audit_uses_current_source_and_deduplicates_unchanged_state(self):
		import json
		f=frappe_stub();f.session=SimpleNamespace(user='worker');f.qb=SimpleNamespace(DocType=lambda dt:Table(),from_=lambda table:Query([]),desc='desc')
		source=Doc(doctype='Work Order',name='WO',docstatus=1,qty=2,required_items=[])
		f.get_doc=Mock(return_value=source);f.db.exists.return_value=True
		event=Doc();event.insert=Mock();f.new_doc=Mock(return_value=event)
		with patch.dict(sys.modules,{'frappe':f}):api=load('events')
		api.record_event(Doc(doctype='Work Order',name='WO',qty=0),'on_change')
		self.assertEqual(json.loads(event.payload)['qty'],2);event.insert.assert_called_once_with(ignore_permissions=True);self.assertFalse(api.INTERNAL.get())
		f.get_doc.assert_called_with('Work Order','WO',for_update=True)
		rows=[{'reference_doctype':'Work Order','reference_name':'WO','payload':event.payload,'fingerprint':event.fingerprint}]
		f.qb.from_=lambda table:Query(rows)
		api.record_event(source,'on_change');self.assertEqual(event.insert.call_count,1)
