import base64
import importlib.util
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


def load(name,path=None):
	spec=importlib.util.spec_from_file_location(name,ROOT/(path or f'erpnext/svoenrav/{name}.py'))
	module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Doc(dict):
	def __init__(self,**values):
		super().__init__(values)
		for key in ('check_permission','apply_fieldlevel_read_permissions','save','insert'):
			object.__setattr__(self,key,Mock())
		object.__setattr__(self,'meta',Mock());self.meta.get_permlevel_access.return_value=[0]
	def __getattr__(self,key):
		if key in self:return self[key]
		raise AttributeError(key)
	def __setattr__(self,key,value):self[key]=value
	def as_dict(self):return dict(self)
	def is_new(self):return self.get('__islocal',True)
	def set(self,key,value):self[key]=value
	def db_set(self,values,**kwargs):self.update(values)
	def get_permlevel_access(self,ptype):return [0]
	def append(self,key,value):self.setdefault(key,[]).append(Doc(**value))


rules=load('product_rules')
flow=load('flow')


class ProductRulesTests(unittest.TestCase):
	def test_global_numbers_keep_leading_zeroes_and_grow_after_width(self):
		self.assertEqual(rules.number_block(98,3,2),[(98,'98'),(99,'99'),(100,'100')])
		self.assertEqual(rules.number_block(1,2,6),[(1,'000001'),(2,'000002')])

	def test_units_and_ranges_reject_fraction_bool_missing_and_nonfinite(self):
		for value in (None,True,0,-1,'NaN','Infinity','0.5'):
			with self.assertRaises(ValueError):rules.whole(value)
		with self.assertRaises(ValueError):rules.number_block(999999999,2,6)
		with self.assertRaises(ValueError):rules.number_block(1,201,6)

	def test_model_code_and_image_urls_are_not_executable_or_external(self):
		self.assertEqual(rules.model_code(' СУМКА-01 '),'СУМКА-01')
		for code in ('<script>','A/B','','A'*81):
			with self.assertRaises(ValueError):rules.model_code(code)
		for url in ('https://evil.test/a.jpg','//evil.test/a.jpg','data:image/png;base64,x','/private/files/../x.jpg','/private/files/%2e%2e%2fx.jpg','/private/files/%5cx.jpg','/private/files/x.jpg?x=1'):
			with self.assertRaises(ValueError):rules.image_path(url)
		self.assertEqual(rules.image_path('/private/files/photo.jpg'),'/private/files/photo.jpg')

	def test_identity_is_bound_to_exact_source_row_and_ordinal(self):
		self.assertNotEqual(rules.unit_key('SE','ROW',1),rules.unit_key('SE','ROW',2))
		self.assertNotEqual(rules.unit_key('SE','ROW',1),rules.unit_key('SE-OTHER','ROW',1))


def setup():
	f=ModuleType('frappe');f.PermissionError=PermissionError;f.ValidationError=ValueError;f.DoesNotExistError=LookupError
	f.throw=lambda message,error=ValueError:(_ for _ in ()).throw(error(message))
	f.whitelist=lambda *a,**k:lambda fn:fn;f.has_permission=Mock(return_value=True)
	f.db=Mock();f.get_doc=Mock();f.new_doc=Mock();f.get_list=Mock(return_value=[]);f.get_all=Mock(return_value=[])
	portal=ModuleType('erpnext.svoenrav.portal');portal.require_staff=Mock()
	materials=ModuleType('erpnext.svoenrav.materials');materials.readable=Mock()
	utils=ModuleType('frappe.utils');utils.get_url_to_form=lambda dt,name:'/desk/'+dt.lower().replace(' ','-')+'/'+name
	modules={'frappe':f,'frappe.utils':utils,'erpnext.svoenrav.portal':portal,'erpnext.svoenrav.materials':materials,'erpnext.svoenrav.product_rules':rules,'erpnext.svoenrav.flow':flow}
	ctx=patch.dict(sys.modules,modules);ctx.start()
	return f,portal,materials,ctx


class ProductLifecycleTests(unittest.TestCase):
	def api(self):
		f,p,m,ctx=setup();self.addCleanup(ctx.stop)
		api=load('products')
		sequence=Doc(next_number=100,digits=6,last_issued=99,enabled=1,confirmed=1)
		model=Doc(name='MODEL',title='Сумка',numbered=1,item_code='BAG',main_photo=None)
		item=Doc(name='BAG',has_serial_no=0)
		units={}
		f.get_doc.side_effect=lambda dt,name,**kwargs:sequence if dt==api.SEQUENCE else model if dt==api.MODEL else item if dt=='Item' else units[name]
		f.db.get_value.side_effect=lambda dt,filters,field=None,**kw:'MODEL' if dt==api.MODEL else 'SO' if dt=='Work Order' else None
		def exists(dt,filters):
			if dt!=api.UNIT:return False
			if 'unit_key' in filters:return next((name for name,u in units.items() if u.unit_key==filters['unit_key']),None)
			if 'name' in filters:return any(name in units for name in filters['name'][1])
			return False
		f.db.exists.side_effect=exists
		def new(dt):
			doc=Doc(doctype=dt)
			def insert(**kwargs):
				self.assertTrue(api.INTERNAL.get());self.assertEqual(kwargs['ignore_permissions'],True)
				doc.name=kwargs['set_name'];units[doc.name]=doc
			doc.insert.side_effect=insert
			return doc
		f.new_doc.side_effect=new
		entry=Doc(name='SE',doctype='Stock Entry',purpose='Manufacture',docstatus=1,company='C',work_order='WO',items=[Doc(name='FG-ROW',item_code='BAG',is_finished_item=1,transfer_qty=2),Doc(name='RAW',item_code='LEATHER',is_finished_item=0,transfer_qty=30)])
		return api,f,p,m,sequence,model,item,units,entry

	def test_numbered_cards_follow_exact_finished_quantity_not_material_rows(self):
		api,f,p,m,seq,model,item,units,entry=self.api();api.register_manufacture(entry)
		self.assertEqual(set(units),{'000100','000101'});self.assertEqual(seq.next_number,102)
		self.assertEqual(units['000100'].stock_entry_detail,'FG-ROW');self.assertEqual(units['000101'].ordinal,2)
		self.assertEqual(units['000100'].sales_order,'SO');self.assertFalse(api.INTERNAL.get());f.db.commit.assert_not_called()

	def test_retry_does_not_issue_new_numbers_and_cancel_never_reuses_number(self):
		api,f,p,m,seq,model,item,units,entry=self.api();api.register_manufacture(entry);api.register_manufacture(entry)
		self.assertEqual(seq.next_number,102);f.get_all.return_value=list(units)
		api.cancel_manufacture(entry)
		self.assertEqual({u.status for u in units.values()},{'Выпуск отменён'});self.assertEqual(seq.next_number,102)
		entry.name='SE-AMENDED';api.register_manufacture(entry)
		self.assertEqual(set(units),{'000100','000101','000102','000103'})

	def test_unconfirmed_start_and_noninteger_output_block_before_card_insertion(self):
		for case in ('unconfirmed','fraction'):
			api,f,p,m,seq,model,item,units,entry=self.api()
			if case=='unconfirmed':seq.confirmed=0
			else:entry['items'][0]['transfer_qty']='0.5'
			with self.assertRaises(ValueError):api.register_manufacture(entry)
			self.assertEqual(units,{});f.new_doc.assert_not_called()

	def test_non_manufacture_and_unmapped_items_do_not_allocate(self):
		api,f,p,m,seq,model,item,units,entry=self.api();entry.purpose='Material Transfer for Manufacture';api.register_manufacture(entry)
		self.assertEqual(seq.next_number,100);entry.purpose='Manufacture';f.db.get_value.return_value=None;f.db.get_value.side_effect=None
		api.register_manufacture(entry);self.assertEqual(units,{})

	def test_partial_existing_set_is_not_silently_repaired(self):
		api,f,p,m,seq,model,item,units,entry=self.api();units['OLD']=Doc(unit_key=rules.unit_key('SE','FG-ROW',1))
		with self.assertRaises(ValueError):api.register_manufacture(entry)
		self.assertEqual(seq.next_number,100)

	def test_cancelled_model_still_numbers_existing_production_and_title_is_frozen(self):
		api,f,p,m,seq,model,item,units,entry=self.api();model.archived=1;api.register_manufacture(entry)
		model.title='Новое название';self.assertEqual(units['000100'].model_title,'Сумка')

	def test_concurrent_allocator_issues_disjoint_blocks_under_row_lock(self):
		api,f,p,m,seq,model,item,units,entry=self.api();guard=threading.Lock();start=threading.Barrier(2)
		def locked_get(dt,name,**kwargs):
			self.assertTrue(kwargs.get('for_update'));guard.acquire();return seq
		f.get_doc.side_effect=locked_get
		def allocate(_):
			start.wait()
			try:return api.reserve_numbers(2)
			finally:guard.release()
		with ThreadPoolExecutor(2) as pool:blocks=list(pool.map(allocate,range(2)))
		self.assertEqual({n for block in blocks for n,_ in block},{100,101,102,103});self.assertEqual(seq.next_number,104)

	def test_serialised_item_requires_exact_native_serials(self):
		api,f,p,m,seq,model,item,units,entry=self.api();item.has_serial_no=1
		serial=ModuleType('erpnext.stock.serial_batch_bundle');serial.get_serial_nos_from_bundle=Mock(return_value=['ONLY-ONE'])
		with patch.dict(sys.modules,{'erpnext.stock.serial_batch_bundle':serial}),self.assertRaises(ValueError):api.register_manufacture(entry)
		self.assertEqual(units,{})

	def test_guest_guard_stops_registry_before_database_access(self):
		api,f,p,m,*_=self.api();p.require_staff.side_effect=PermissionError
		for callback in (api.get_units,lambda:api.get_unit('000100'),api.numbering_state):
			with self.assertRaises(PermissionError):callback()
		f.get_list.assert_not_called()


class ModelAndNumberingControllerTests(unittest.TestCase):
	def controller(self,name):
		f,p,m,ctx=setup();self.addCleanup(ctx.stop)
		document=ModuleType('frappe.model.document');document.Document=Doc
		catalog=ModuleType('erpnext.svoenrav.catalog');catalog.photo_file=Mock()
		products=ModuleType('erpnext.svoenrav.products')
		from contextvars import ContextVar
		products.INTERNAL=ContextVar('test_unit_context',default=False)
		context=patch.dict(sys.modules,{'frappe.model.document':document,'erpnext.svoenrav.catalog':catalog,'erpnext.svoenrav.products':products});context.start();self.addCleanup(context.stop)
		module=load('controller',f'erpnext/svoenrav/doctype/{name}/{name}.py')
		return module,f,m,catalog,products

	def test_manual_unit_creation_edit_delete_and_rename_are_rejected(self):
		module,f,m,catalog,products=self.controller('svoenrav_product_unit');doc=module.SVOENRAVProductUnit()
		with self.assertRaises(PermissionError):doc.validate()
		with self.assertRaises(ValueError):doc.on_trash()
		with self.assertRaises(ValueError):doc.before_rename()

	def test_counter_cannot_be_reset_after_issue_and_start_requires_confirmation(self):
		module,f,*_=self.controller('svoenrav_product_sequence')
		old=Doc(last_issued=50,next_number=51,digits=6)
		f.get_doc.return_value=old
		doc=module.SVOENRAVProductSequence(name='main',doctype='SVOENRAV Product Sequence',series_key='main',next_number=1,digits=6,enabled=1,confirmed=0,last_issued=0,__islocal=False)
		with self.assertRaises(ValueError):doc.validate()
		doc.confirmed=1
		with self.assertRaises(ValueError):doc.validate()
		doc.next_number=51;doc.validate();self.assertEqual(doc.last_issued,50)

	def test_existing_unit_prevents_model_item_change_or_numbering_disable(self):
		module,f,m,*_=self.controller('svoenrav_model')
		item=Doc(is_stock_item=1,disabled=0,has_variants=0,stock_uom='шт');uom=Doc(must_be_whole_number=1)
		m.readable.side_effect=lambda dt,name:item if dt=='Item' else uom
		f.db.exists.return_value=True
		doc=module.SVOENRAVModel(name='MODEL',model_code='MODEL',title='Сумка',item_code='OTHER',numbered=1,photos=[],__islocal=False)
		doc.get_doc_before_save=Mock(return_value=Doc(item_code='BAG',numbered=1))
		with self.assertRaises(ValueError):doc.validate()

	def test_duplicate_photos_and_fractional_stock_uom_are_rejected(self):
		module,f,m,*_=self.controller('svoenrav_model')
		m.readable.side_effect=lambda dt,name:Doc(is_stock_item=1,disabled=0,has_variants=0,stock_uom='шт') if dt=='Item' else Doc(must_be_whole_number=1)
		doc=module.SVOENRAVModel(name='MODEL',model_code='MODEL',title='Сумка',item_code='BAG',numbered=1,photos=[Doc(image='/private/files/a.jpg'),Doc(image='/private/files/a.jpg')])
		with self.assertRaises(ValueError):doc.validate()
		doc.photos=[];m.readable.side_effect=lambda dt,name:Doc(is_stock_item=1,disabled=0,has_variants=0,stock_uom='дм²') if dt=='Item' else Doc(must_be_whole_number=0)
		with self.assertRaises(ValueError):doc.validate()


class CatalogAPITests(unittest.TestCase):
	def api(self):
		f,p,m,ctx=setup();self.addCleanup(ctx.stop);return load('catalog'),f,p,m

	def test_guest_and_no_create_permission_do_not_create_item(self):
		api,f,p,m=self.api();p.require_staff.side_effect=PermissionError
		with self.assertRaises(PermissionError):api.get_models()
		f.get_list.assert_not_called();p.require_staff.side_effect=None;f.has_permission.return_value=False
		with self.assertRaises(PermissionError):api.create_model('MODEL','Сумка')
		f.new_doc.assert_not_called()

	def test_only_parent_attached_private_raster_file_is_accepted(self):
		api,f,p,m=self.api();f.db.get_value.return_value='FILE'
		file=Doc(file_url='/private/files/a.png',attached_to_doctype='SVOENRAV Model',attached_to_name='MODEL',is_private=1,file_name='a.png',file_size=10)
		m.readable.return_value=file
		self.assertEqual(api.photo_file('MODEL',file.file_url),file)
		for key,value in [('attached_to_name','OTHER'),('is_private',0),('file_name','a.svg'),('file_size',20*1024*1024)]:
			old=file[key];file[key]=value
			with self.assertRaises(ValueError):api.photo_file('MODEL',file.file_url)
			file[key]=old

	def test_real_png_is_verified_and_nonimage_is_rejected(self):
		api,f,p,m=self.api();f.db.get_value.return_value='FILE'
		image_url=json.loads((ROOT/'svoenrav/preview/fixtures.json').read_text())['models'][0]['main_photo']
		file=Doc(file_url='/private/files/a.png',attached_to_doctype='SVOENRAV Model',attached_to_name='MODEL',is_private=1,file_name='a.png',file_size=100)
		file.get_content=Mock(return_value=base64.b64decode(image_url.split(',')[1]));m.readable.return_value=file
		api.photo_file('MODEL',file.file_url,verify=True)
		file.get_content.return_value=b'<script>alert(1)</script>'
		with self.assertRaises(ValueError):api.photo_file('MODEL',file.file_url,verify=True)

	def test_stale_editor_cannot_overwrite_changed_model(self):
		api,f,p,m=self.api();doc=Doc(name='MODEL',modified='NEW');f.get_doc.return_value=doc
		with self.assertRaises(ValueError):api.update_model('MODEL',title='OLD',modified='OLD')
		doc.save.assert_not_called()

	def test_remove_photo_detaches_only_and_keeps_file_bytes(self):
		api,f,p,m=self.api();doc=Doc(name='MODEL',main_photo='/private/files/a.png',photos=[Doc(image='/private/files/a.png'),Doc(image='/private/files/b.png')]);f.get_doc.return_value=doc
		api.model_data=Mock(return_value={})
		api.remove_photo('MODEL','/private/files/a.png')
		self.assertEqual(doc.main_photo,'/private/files/b.png');self.assertEqual(len(doc.photos),1);doc.save.assert_called_once_with()
		self.assertFalse(hasattr(f,'delete_doc'))

	def test_missing_new_item_permission_and_invalid_uom_stop_before_item_insert(self):
		api,f,p,m=self.api();f.has_permission.side_effect=lambda dt,ptype:dt!='Item'
		with self.assertRaises(PermissionError):api.create_model('MODEL','Сумка')
		f.new_doc.assert_not_called()

	def test_model_list_uses_permission_aware_query_and_reports_pagination(self):
		api,f,p,m=self.api();f.get_list.return_value=[{'name':f'M{i}'} for i in range(25)];api.model_data=Mock(return_value={'name':'M'})
		result=api.get_models(search='Сумка',state='archived')
		self.assertTrue(result['has_more']);self.assertEqual(len(result['rows']),24)
		self.assertEqual(f.get_list.call_args.kwargs['filters'],{'archived':1});self.assertNotIn('ignore_permissions',f.get_list.call_args.kwargs)


class ProductAccessTests(unittest.TestCase):
	def api(self):
		f,p,m,ctx=setup();self.addCleanup(ctx.stop)
		return load('product_access'),f

	def test_unit_requires_every_source_read_and_forbids_writes(self):
		api,f=self.api();doc=Doc(model='MODEL',manufacture_entry='SE',item_code='BAG')
		f.get_doc.side_effect=lambda dt,name:Doc(doctype=dt,name=name)
		f.has_permission.side_effect=lambda dt,*a,**k:dt!='Stock Entry'
		self.assertFalse(api.unit_permission(doc,'read',user='operator'))
		f.has_permission.return_value=True;f.has_permission.side_effect=None
		self.assertTrue(api.unit_permission(doc,'read',user='operator'))
		for action in ('create','write','delete','cancel'):
			self.assertFalse(api.unit_permission(doc,action,user='operator'))

	def test_operator_does_not_need_hidden_order_link_but_owner_does(self):
		api,f=self.api();doc=Doc(model='MODEL',manufacture_entry='SE',item_code='BAG',sales_order='SO')
		f.get_doc.side_effect=lambda dt,name:Doc(doctype=dt,name=name)
		f.has_permission.side_effect=lambda dt,*a,**k:dt!='Sales Order'
		self.assertTrue(api.unit_permission(doc,'read'))
		doc.meta.get_permlevel_access.return_value=[0,1]
		self.assertFalse(api.unit_permission(doc,'read'))

	def test_missing_deleted_native_serial_does_not_hide_cancelled_card(self):
		api,f=self.api();doc=Doc(model='MODEL',manufacture_entry='SE',item_code='BAG',native_serial_no='SN',status='Выпуск отменён')
		doc.meta.get_permlevel_access.return_value=[0,1];f.db.exists.return_value=False
		f.get_doc.side_effect=lambda dt,name:Doc(doctype=dt,name=name)
		self.assertTrue(api.unit_permission(doc,'read'))
		self.assertNotIn('Serial No',[call.args[0] for call in f.get_doc.call_args_list])

	def test_model_does_not_bypass_item_permissions(self):
		api,f=self.api();f.has_permission.return_value=False
		self.assertFalse(api.model_permission(Doc(item_code='BAG'),'read'))
