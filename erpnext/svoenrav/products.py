# License: GNU General Public License v3. See license.txt
"""Immutable workshop identities, allocated atomically with native manufacture."""
from contextvars import ContextVar
import frappe
from frappe.utils import get_url_to_form
from erpnext.svoenrav.flow import validate_source, visible_dict
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.product_rules import MAX_BATCH, number_block, unit_key, whole

INTERNAL = ContextVar('svoenrav_product_unit_write', default=False)
UNIT = 'SVOENRAV Product Unit'
MODEL = 'SVOENRAV Model'
SEQUENCE = 'SVOENRAV Product Sequence'


def setup():
	if not frappe.db.exists(SEQUENCE,'main'):
		doc=frappe.new_doc(SEQUENCE)
		doc.update({'series_key':'main','next_number':1,'digits':6,'last_issued':0,'enabled':0,'confirmed':0})
		doc.insert()


def reserve_numbers(count):
	sequence=frappe.get_doc(SEQUENCE,'main',for_update=True)
	if not sequence.get('enabled') or not sequence.get('confirmed'):
		frappe.throw('Перед выпуском номерных моделей владелец должен настроить следующий свободный номер и включить нумерацию SVOENRAV.',frappe.ValidationError)
	try:
		block=number_block(sequence.next_number,count,sequence.digits)
	except ValueError as exc:
		frappe.throw(str(exc),frappe.ValidationError)
	if frappe.db.exists(UNIT,{'name':['in',[name for _,name in block]]}):
		frappe.throw('Номер уже занят. Проверьте прежний учёт и последовательность; номер не пропущен автоматически.',frappe.ValidationError)
	sequence.db_set({'next_number':block[-1][0]+1,'last_issued':block[-1][0]},update_modified=False)
	return block


def manufacture_plan(doc):
	result=[]
	for row in doc.get('items') or []:
		if not row.get('is_finished_item'):
			continue
		model_name=frappe.db.get_value(MODEL,{'item_code':row.item_code},'name')
		if not model_name:
			continue
		model=frappe.get_doc(MODEL,model_name)
		if not model.get('numbered'):
			continue
		try:
			count=whole(row.get('transfer_qty'),'Количество экземпляров',maximum=MAX_BATCH)
		except ValueError as exc:
			frappe.throw(str(exc),frappe.ValidationError)
		item=frappe.get_doc('Item',row.item_code)
		serials=[]
		if item.get('has_serial_no'):
			from erpnext.stock.serial_batch_bundle import get_serial_nos_from_bundle
			serials=get_serial_nos_from_bundle(row.get('serial_and_batch_bundle'))
			if len(serials)!=count or len(set(serials))!=count:
				frappe.throw('Количество серийных номеров ERPNext не совпадает с выпуском. Карточки не созданы.',frappe.ValidationError)
			for name in sorted(serials):
				frappe.db.get_value('Serial No',name,'name',for_update=True)
				if frappe.db.exists(UNIT,{'native_serial_no':name,'status':'Выпущено','manufacture_entry':['!=',doc.name]}):
					frappe.throw('Серийный номер уже связан с активным номерным изделием.',frappe.ValidationError)
			if any(frappe.db.get_value('Serial No',name,'item_code')!=row.item_code for name in serials):
				frappe.throw('Серийный номер относится к другой номенклатуре.',frappe.ValidationError)
		for ordinal in range(1,count+1):
			result.append({'model':model.name,'model_title':model.title,'item_code':row.item_code,'photo_at_issue':model.get('main_photo'),'stock_entry_detail':row.name,'ordinal':ordinal,'unit_key':unit_key(doc.name,row.name,ordinal),'native_serial_no':serials[ordinal-1] if serials else None})
	if len(result)>MAX_BATCH:
		frappe.throw(f'В одном выпуске поддерживается до {MAX_BATCH} номерных экземпляров. Разделите выпуск.',frappe.ValidationError)
	return result


def register_manufacture(doc, method=None):
	if doc.get('purpose')!='Manufacture' or doc.docstatus!=1:
		return
	plan=manufacture_plan(doc)
	if not plan:
		return
	existing=[frappe.db.exists(UNIT,{'unit_key':row['unit_key']}) for row in plan]
	if all(existing):
		return  # Retry never issues a second identity for the same finished row.
	if any(existing):
		frappe.throw('Для выпуска найден неполный набор карточек. Проверьте данные; новые номера не выделены.',frappe.ValidationError)
	block=reserve_numbers(len(plan))
	sales_order=frappe.db.get_value('Work Order',doc.work_order,'sales_order') if doc.get('work_order') else None
	token=INTERNAL.set(True)
	try:
		for row,(number,name) in zip(plan,block,strict=True):
			unit=frappe.new_doc(UNIT)
			unit.update({**row,'product_number':number,'company':doc.company,'manufacture_entry':doc.name,'work_order':doc.get('work_order'),'sales_order':sales_order,'status':'Выпущено'})
			# Trusted, generated metadata of an authorised native manufacturing post.
			# REST cannot enter INTERNAL; no stock/serial ledger is replaced here.
			unit.insert(ignore_permissions=True,set_name=name)
	finally:
		INTERNAL.reset(token)


def cancel_manufacture(doc, method=None):
	if doc.get('purpose')!='Manufacture':
		return
	names=frappe.get_all(UNIT,filters={'manufacture_entry':doc.name},pluck='name')
	token=INTERNAL.set(True)
	try:
		for name in names:
			unit=frappe.get_doc(UNIT,name,for_update=True)
			if unit.status!='Выпуск отменён':
				unit.status='Выпуск отменён';unit.save(ignore_permissions=True)
	finally:
		INTERNAL.reset(token)


def unit_data(doc):
	doc.check_permission('read');doc.apply_fieldlevel_read_permissions()
	readable('Stock Entry',doc.manufacture_entry)
	model=readable(MODEL,doc.model)
	readable('Item',doc.item_code)
	keys=('name','product_number','model','model_title','item_code','status','company','manufacture_entry','stock_entry_detail','ordinal','creation')
	data={key:doc.get(key) for key in keys}
	data.update(url=get_url_to_form(UNIT,doc.name),source_url=get_url_to_form('Stock Entry',doc.manufacture_entry),model_url=get_url_to_form(MODEL,model.name),photo=None,work_order=None,sales_order=None,native_serial_no=None)
	for field,doctype in (('work_order','Work Order'),('sales_order','Sales Order'),('native_serial_no','Serial No')):
		if not doc.get(field):
			continue
		try:
			linked=readable(doctype,doc.get(field))
			data[field]={'name':linked.name,'url':get_url_to_form(doctype,linked.name)}
		except (frappe.PermissionError,frappe.DoesNotExistError):
			pass
	if doc.get('photo_at_issue'):
		from erpnext.svoenrav.catalog import photo_file
		try:
			data['photo']=photo_file(doc.model,doc.photo_at_issue).file_url
		except (frappe.PermissionError,frappe.ValidationError,frappe.DoesNotExistError):
			pass
	return data


@frappe.whitelist()
def get_units(search='', start=0, model=None, manufacture_entry=None):
	require_staff()
	if not frappe.has_permission(UNIT,ptype='read'):
		frappe.throw('Нет права чтения номерных изделий.',frappe.PermissionError)
	from erpnext.svoenrav.catalog import page_args
	search,offset=page_args(search,start)
	filters={}
	for field,doctype,value in (('model',MODEL,model),('manufacture_entry','Stock Entry',manufacture_entry)):
		if value:
			readable(doctype,validate_source(value));filters[field]=value
	rows=frappe.get_list(UNIT,filters=filters,or_filters=[[field,'like','%'+search+'%'] for field in ('name','model_title','item_code')] if search else None,fields=['name'],order_by='product_number desc',limit_start=offset,limit_page_length=25)
	result=[]
	for row in rows[:24]:
		try:
			result.append(unit_data(frappe.get_doc(UNIT,row['name'])))
		except frappe.PermissionError:
			continue
	return {'rows':result,'start':offset,'has_more':len(rows)>24,'notice':'Номер присваивается проведённым выпуском. Это внутренний реестр экземпляров, не публичный паспорт и не подтверждение отгрузки.'}


@frappe.whitelist()
def get_unit(number):
	require_staff()
	doc=frappe.get_doc(UNIT,validate_source(number))
	data=unit_data(doc)
	data['history']=None
	if frappe.has_permission('SVOENRAV Operation Event',ptype='read'):
		from erpnext.svoenrav.history import audit_events
		data['history']=audit_events(UNIT,doc.name,visible_dict(doc))
	return data


@frappe.whitelist()
def numbering_state():
	require_staff()
	if not frappe.has_permission(UNIT,ptype='read'):
		frappe.throw('Нет права чтения номерного учёта.',frappe.PermissionError)
	sequence=frappe.get_doc(SEQUENCE,'main')
	can_configure=bool(frappe.has_permission(SEQUENCE,ptype='write',doc=sequence))
	return {'enabled':bool(sequence.enabled and sequence.confirmed),'can_configure':can_configure,'url':get_url_to_form(SEQUENCE,'main') if can_configure else None,'next_number':sequence.next_number if can_configure else None,'last_issued':sequence.last_issued if can_configure else None,'notice':'Перед первым выпуском владелец проверяет прежние номера и задаёт следующий свободный. Сама настройка номера не присваивает.'}
