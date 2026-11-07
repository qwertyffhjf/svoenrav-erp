# License: GNU General Public License v3. See license.txt
import frappe
from frappe.model.document import Document
from erpnext.svoenrav.materials import readable
from erpnext.svoenrav.product_rules import model_code


class SVOENRAVModel(Document):
	def validate(self):
		from erpnext.svoenrav.catalog import photo_file
		try:
			self.model_code = model_code(self.model_code)
		except ValueError as exc:
			frappe.throw(str(exc), frappe.ValidationError)
		if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 140 or len(self.get('description') or '') > 2000:
			frappe.throw('Укажите название до 140 символов, описание — до 2000.', frappe.ValidationError)
		self.title = self.title.strip()
		item = readable('Item', self.item_code)
		if item.get('is_stock_item') != 1 or item.get('disabled') != 0 or item.get('has_variants') != 0:
			frappe.throw('Выберите действующую складскую номенклатуру без шаблона вариантов.', frappe.ValidationError)
		if not item.get('stock_uom'):
			frappe.throw('Складская единица номенклатуры недоступна.', frappe.PermissionError)
		if self.numbered:
			uom = readable('UOM', item.stock_uom)
			if uom.get('must_be_whole_number') != 1:
				frappe.throw('Номерные изделия учитываются в целой складской единице.', frappe.ValidationError)
		if not self.is_new():
			old = self.get_doc_before_save() or frappe.get_doc(self.doctype, self.name)
			if self.model_code != self.name:
				frappe.throw('Артикул модели неизменяем.', frappe.ValidationError)
			if frappe.db.exists('SVOENRAV Product Unit', {'model':self.name}) and (old.item_code != self.item_code or old.numbered != self.numbered):
				frappe.throw('У выпущенной модели нельзя менять номенклатуру или отключать нумерацию.', frappe.ValidationError)
		if len(self.get('photos') or []) > 12:
			frappe.throw('В галерее допускается до 12 фотографий.', frappe.ValidationError)
		images = []
		for row in self.get('photos') or []:
			if not isinstance(row.get('caption') or '', str) or len(row.get('caption') or '') > 140:
				frappe.throw('Подпись фотографии — до 140 символов.', frappe.ValidationError)
			if row.image in images:
				frappe.throw('Фотография повторяется в галерее.', frappe.ValidationError)
			images.append(row.image)
		urls=set(images + ([self.main_photo] if self.get('main_photo') else []))
		if len(urls)>12:
			frappe.throw('Допускается до 12 фотографий вместе с обложкой.', frappe.ValidationError)
		for url in urls:
			photo_file(self.name, url, verify=True)

	def before_rename(self, *args, **kwargs):
		frappe.throw('Артикул модели неизменяем.', frappe.ValidationError)

	def on_trash(self):
		frappe.throw('Модели переводятся в архив, а не удаляются.', frappe.ValidationError)
