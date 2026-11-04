# License: GNU General Public License v3. See license.txt
"""Freeze normative BOM trees, routes and drawing metadata; no file-byte copy."""
import hashlib
import json
import frappe
from erpnext.svoenrav.materials import readable


def build_pack(order):
	boms = {}
	visiting = set()
	def visit(name):
		if name in visiting:
			frappe.throw("Цикл в структуре BOM.", frappe.ValidationError)
		if name in boms:
			return
		if len(boms) >= 200:
			frappe.throw("Пакет превышает 200 BOM. Фиксация остановлена.", frappe.ValidationError)
		visiting.add(name)
		bom = readable("BOM", name)
		if bom.docstatus != 1:
			frappe.throw("Нормы требуют проведённых версий BOM.", frappe.ValidationError)
		items = [{k: row.get(k) for k in ("item_code", "qty", "uom", "stock_qty", "stock_uom", "bom_no", "operation")} for row in bom.get("items") or []]
		routes = [{k: row.get(k) for k in ("operation", "workstation", "time_in_mins", "sequence_id")} for row in bom.get("operations") or []]
		boms[name] = {"name": name, "item": bom.item, "quantity": bom.quantity, "uom": bom.get("uom"), "modified": str(bom.modified), "items": items, "operations": routes}
		if sum(len(b["items"]) for b in boms.values()) > 5000:
			frappe.throw("Пакет превышает 5000 строк BOM.", frappe.ValidationError)
		for row in items:
			if row.get("bom_no"):
				visit(row["bom_no"])
		visiting.remove(name)
	visit(order.bom_no)
	attachments = []
	if frappe.has_permission("File", ptype="read"):
		for doctype, names in (("Work Order", [order.name]), ("BOM", sorted(boms))):
			rows = frappe.get_list("File", filters={"attached_to_doctype": doctype, "attached_to_name": ["in", names]}, fields=["name", "file_name", "file_url", "content_hash", "attached_to_name"], limit_page_length=501)
			if len(rows) > 500:
				frappe.throw("Слишком много вложений для фиксации пакета.", frappe.ValidationError)
			attachments.extend(dict(row) for row in rows)
	data = {"schema": 1, "boms": boms, "operations": [{k: row.get(k) for k in ("operation", "workstation", "time_in_mins", "sequence_id")} for row in order.get("operations") or []], "attachments": attachments, "attachment_scope": "Метаданные и исходный content_hash доступных файлов; файлы не копируются."}
	payload = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
	return payload, hashlib.sha256(payload.encode()).hexdigest()
