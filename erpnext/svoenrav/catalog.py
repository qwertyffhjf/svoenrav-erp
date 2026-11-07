# License: GNU General Public License v3. See license.txt
"""Private model gallery with permission-checked native Item/File links."""
import os
import frappe
from frappe.utils import get_url_to_form
from erpnext.svoenrav.flow import validate_source, visible_dict
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.portal import require_staff
from erpnext.svoenrav.product_rules import image_path, model_code, whole

MODEL = 'SVOENRAV Model'
UNIT = 'SVOENRAV Product Unit'
SEQUENCE = 'SVOENRAV Product Sequence'


def photo_file(model, url, verify=False):
	try:
		url = image_path(url)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)
	name = frappe.db.get_value('File', {'file_url':url}, 'name')
	if not name:
		frappe.throw('Загруженный файл фотографии не найден.', frappe.ValidationError)
	file = readable('File', name)
	if file.get('file_url')!=url:
		frappe.throw('Ссылка фотографии недоступна по правам.',frappe.PermissionError)
	if file.get('attached_to_doctype') != MODEL or file.get('attached_to_name') != model or file.get('is_private') != 1:
		frappe.throw('Фотография должна быть закрытым файлом этой модели. Сначала сохраните модель, затем загрузите фото.', frappe.ValidationError)
	if os.path.splitext(file.get('file_name') or '')[1].lower() not in ('.jpg','.jpeg','.png','.webp') or not file.get('file_size') or file.file_size > 10 * 1024 * 1024:
		frappe.throw('Фотография: JPG, PNG или WEBP до 10 МБ.', frappe.ValidationError)
	if verify:
		from io import BytesIO
		from PIL import Image
		try:
			with Image.open(BytesIO(file.get_content())) as image:
				if image.format not in ('JPEG','PNG','WEBP'):
					raise ValueError('Unsupported image')
				image.verify()
		except (OSError, ValueError, Image.DecompressionBombError):
			frappe.throw('Файл не является корректной фотографией JPG, PNG или WEBP.', frappe.ValidationError)
	return file


def model_data(doc, gallery=True):
	doc.check_permission('read')
	doc.apply_fieldlevel_read_permissions()
	item = readable('Item', doc.item_code)
	data = {key:doc.get(key) for key in ('name','model_code','title','description','archived','numbered','item_code')}
	data['modified']=str(doc.get('modified') or '')
	data.update(url=get_url_to_form(MODEL,doc.name), stock_uom=item.get('stock_uom'), item_group=item.get('item_group'), photos=[], main_photo=None, can_edit=bool(frappe.has_permission(MODEL,ptype='write',doc=doc)))
	urls = [(doc.get('main_photo'),'Обложка')] + [(row.get('image'),row.get('caption') or '') for row in doc.get('photos') or []]
	seen = set()
	for url, caption in urls:
		if not url or url in seen:
			continue
		seen.add(url)
		try:
			file = photo_file(doc.name,url)
		except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
			continue
		data['photos'].append({'url':file.file_url,'caption':caption})
		if not gallery:
			break
	if data['photos']:
		data['main_photo'] = data['photos'][0]['url']
	return data


def page_args(search, start):
	if not isinstance(search,str) or len(search) > 100:
		frappe.throw('Поиск — текст до 100 символов.',frappe.ValidationError)
	try:
		offset = whole(start, 'Страница', minimum=0, maximum=10000)
	except ValueError as exc:
		frappe.throw(str(exc),frappe.ValidationError)
	return search.strip(), offset


@frappe.whitelist()
def get_models(search='', start=0, state='active'):
	require_staff()
	if not frappe.has_permission(MODEL,ptype='read'):
		frappe.throw('Нет права чтения моделей.',frappe.PermissionError)
	search, offset = page_args(search,start)
	if state not in ('active','archived','all'):
		frappe.throw('Неизвестный фильтр моделей.',frappe.ValidationError)
	filters = {} if state == 'all' else {'archived':int(state=='archived')}
	rows = frappe.get_list(MODEL,filters=filters,or_filters=[[field,'like','%'+search+'%'] for field in ('model_code','title','item_code')] if search else None,fields=['name'],order_by='title asc, name asc',limit_start=offset,limit_page_length=25)
	result=[]
	for row in rows[:24]:
		try:
			result.append(model_data(frappe.get_doc(MODEL,row['name']),gallery=False))
		except frappe.PermissionError:
			continue
	return {'rows':result,'start':offset,'has_more':len(rows)>24,'can_create':bool(frappe.has_permission(MODEL,ptype='create')),'notice':'Одна карточка модели связана с одной складской номенклатурой. Учитываемые отдельно варианты оформляются отдельными карточками.'}


@frappe.whitelist()
def get_model(model):
	require_staff()
	try:
		name=validate_source(model)
	except ValueError as exc:
		frappe.throw(str(exc),frappe.ValidationError)
	return model_data(frappe.get_doc(MODEL,name))


@frappe.whitelist(methods=['POST'])
def create_model(code, title, item_code=None, stock_uom=None, item_group=None, description=''):
	require_staff()
	if not frappe.has_permission(MODEL,ptype='create'):
		frappe.throw('Нет права создания модели.',frappe.PermissionError)
	try:
		code=model_code(code)
	except ValueError as exc:
		frappe.throw(str(exc),frappe.ValidationError)
	if not isinstance(title,str) or not title.strip() or len(title)>140 or not isinstance(description,str) or len(description)>2000:
		frappe.throw('Укажите название до 140 символов и описание до 2000.',frappe.ValidationError)
	if not item_code:
		if not frappe.has_permission('Item',ptype='create'):
			frappe.throw('Выберите существующую номенклатуру или получите право создания Item.',frappe.PermissionError)
		for doctype,name in (('UOM',stock_uom),('Item Group',item_group)):
			try:
				name=validate_source(name)
			except ValueError as exc:
				frappe.throw(str(exc),frappe.ValidationError)
			readable(doctype,name)
		item=frappe.new_doc('Item')
		item.update({'item_code':code,'item_name':title.strip(),'stock_uom':stock_uom,'item_group':item_group,'is_stock_item':1})
		item.insert()
		item_code=item.name
	else:
		readable('Item',validate_source(item_code))
	doc=frappe.new_doc(MODEL)
	doc.update({'model_code':code,'title':title.strip(),'item_code':item_code,'description':description,'numbered':1})
	doc.insert()
	return model_data(doc)


@frappe.whitelist(methods=['POST'])
def update_model(model, title=None, description=None, archived=None, modified=None):
	require_staff()
	doc=frappe.get_doc(MODEL,validate_source(model),for_update=True);doc.check_permission('read');doc.check_permission('write')
	if modified is not None and str(doc.modified)!=modified:
		frappe.throw('Карточка уже изменена. Откройте её заново перед сохранением.',frappe.ValidationError)
	if archived is not None and archived not in (0,1,'0','1'):
		frappe.throw('Архив задаётся флажком.',frappe.ValidationError)
	for key,value in (('title',title),('description',description),('archived',int(archived) if archived is not None else None)):
		if value is not None:
			doc.set(key,value)
	doc.save()
	return model_data(doc)


@frappe.whitelist(methods=['POST'])
def attach_photo(model, file_url, caption=''):
	require_staff()
	doc=frappe.get_doc(MODEL,validate_source(model),for_update=True);doc.check_permission('write')
	photo_file(doc.name,file_url,verify=True)
	if not any(row.image==file_url for row in doc.get('photos') or []):
		doc.append('photos',{'image':file_url,'caption':caption})
	if not doc.get('main_photo'):
		doc.main_photo=file_url
	doc.save()
	return model_data(doc)


@frappe.whitelist(methods=['POST'])
def set_cover(model, file_url):
	require_staff()
	doc=frappe.get_doc(MODEL,validate_source(model),for_update=True);doc.check_permission('write')
	if file_url not in [row.image for row in doc.get('photos') or []]:
		frappe.throw('Выберите фотографию из галереи.',frappe.ValidationError)
	doc.main_photo=file_url;doc.save()
	return model_data(doc)


@frappe.whitelist(methods=['POST'])
def remove_photo(model, file_url):
	require_staff()
	doc=frappe.get_doc(MODEL,validate_source(model),for_update=True);doc.check_permission('write')
	doc.set('photos',[row for row in doc.get('photos') or [] if row.image!=file_url])
	if doc.get('main_photo')==file_url:
		doc.main_photo=doc.photos[0].image if doc.photos else None
	doc.save()  # Only detach from gallery; never delete file bytes.
	return model_data(doc)
