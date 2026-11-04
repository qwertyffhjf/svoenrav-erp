#!/usr/bin/env python3
"""Build a self-contained preview from production template/JS and marked fixtures.

Development requires Jinja2. Opening the generated HTML requires only a browser.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from jinja2 import DictLoader, Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "svoenrav/preview"
OUTPUT = ROOT / "SVOENRAV_PREVIEW.html"


def pure_module(name):
	spec = importlib.util.spec_from_file_location("erpnext.svoenrav." + name, ROOT / f"erpnext/svoenrav/{name}.py")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def demo_data():
	flow = pure_module("flow")
	with patch.dict(sys.modules, {"erpnext.svoenrav.flow": flow}):
		menu = pure_module("menu")
	materials = pure_module("material_rules")
	cutting = pure_module("cutting_rules")
	demo = json.loads((PREVIEW / "fixtures.json").read_text())
	demo["operations"] = [{"key": key, **value} for key, value in flow.OPERATIONS.items()]
	wo = demo["work_order"]
	wo["url"] = "/desk/work-order/" + wo["name"]
	queue = pure_module("queue_rules")
	demo["queue_row"] = queue.sort_queue([wo], {wo["name"]:{"priority":10}}, "2026-11-04")[0]
	demo["coverage"] = {
		**materials.coverage(materials.group_requirements(demo["material_rows"]), {(demo["material"],demo["warehouse"]):demo["balance"]}),
		"work_order":wo["name"],"url":wo["url"],"checked_at":"ТЕСТОВЫЙ СНИМОК · 04.11.2026","review_required":False,
		"notice":"Тестовые данные. Проверка не создаёт резерв; свободный остаток доступен другим заданиям.",
	}
	empty = {"allowed":True,"rows":[],"has_more":False}
	demo["order_card"] = {"order":demo["sales_order"],"url":"/desk/sales-order/"+demo["sales_order"]["name"],"items":[{"item_name":wo["item_name"],"qty":5,"uom":"шт","delivered_qty":1,"delivery_date":wo["expected_delivery_date"]}],"production":{"allowed":True,"rows":[wo],"has_more":False},"stock":empty,"deliveries":empty,"invoices":empty}
	cases = [demo["cutting"], {"area_unit":"м²","input_area":"0.3","used_area":"0.1","reusable_area":"0.1","waste_area":"0.1"}, {"area_unit":"см²","input_area":"1e3","used_area":600,"reusable_area":300,"waste_area":100}]
	for value in (None,True,-1,"NaN","Infinity","1e-7","1.0000001"):
		cases.append({**demo["cutting"],"used_area":value})
	cases += [{**demo["cutting"],"waste_area":3},{**demo["cutting"],"area_unit":"шт"},{"area_unit":"дм²","input_area":0,"used_area":0,"reusable_area":0,"waste_area":0}]
	demo["cutting_cases"] = []
	for case in cases:
		try:
			result = cutting.cutting_balance(case)
			demo["cutting_cases"].append({"input":case,"valid":True,"result":result})
		except ValueError:
			demo["cutting_cases"].append({"input":case,"valid":False})
	return demo, menu.normalise_actions(None)


BASE_CSS = """
*{box-sizing:border-box}body{margin:0;background:#fafbfa;color:#24312b;font:15px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif}a{color:#21372f}button,input,select,textarea{font:inherit}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.5}.btn{border:1px solid #ccd8d0;border-radius:6px;padding:9px 14px;background:#fff;color:#21372f}.btn-primary{background:#21372f;color:#fff;border-color:#21372f}.btn-xs{padding:5px 8px;font-size:12px}.form-group{margin:0 0 16px}.form-group label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}.form-group input,.form-group select,.form-group textarea{width:100%;border:1px solid #ccd8d0;border-radius:6px;padding:10px;background:white;color:#24312b}.form-group small{display:block;font-size:12px;color:#647168;margin-top:5px}.text-muted{color:#647168}.preview-banner{background:#fff1ce;border-bottom:1px solid #d7bd70;padding:14px 20px;position:relative}.preview-banner strong{display:block}.preview-banner p{font-size:13px;margin:6px 0}.preview-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.preview-stage{padding:12px 20px;max-width:1400px;margin:auto}#preview-message{color:#8b341c;white-space:pre-line;margin-top:8px}#preview-document-body{max-width:1000px;margin:20px auto}pre{background:#edf2ef;padding:16px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}.preview-footnote{color:#647168;font-size:12px;padding:16px 20px;overflow-wrap:anywhere}[hidden]{display:none!important}@media(max-width:600px){.preview-stage{padding:8px}.preview-banner{padding:12px}.preview-toolbar .btn{flex:1}}
"""


def escape_script(source):
	return source.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")


def render():
	demo, actions = demo_data()
	for action in actions:
		if action.get("operation"):
			action["url"] = "/desk/svoenrav-workshop?" + urlencode({"operation":action["operation"]})
		else:
			slug = action["doctype"].lower().replace(" ", "-")
			action["url"] = "/desk/" + slug + ("/new-" + slug if action["mode"] == "new" else "")
	context = {"brand_name":"SVOENRAV","brand_description":"Кожевенная мастерская · ТЕСТОВЫЕ ДАННЫЕ","brand_colour":"#21372F","actions":actions,"quick_actions":[a for a in actions if a.get("section")=="quick"],"module_actions":[a for a in actions if a.get("section")!="quick"],"work_orders":[demo["work_order"]],"can_read_work_orders":True,"can_read_orders":True,"can_configure":True,"settings_url":"/desk/svoenrav-settings","customise_url":"/desk/customize-form","workshop_url":"/desk/svoenrav-workshop","action_warnings":[]}
	template_path = ROOT / "erpnext/www/svoenrav/index.html"
	page_path = ROOT / "erpnext/svoenrav/page/svoenrav_workshop/svoenrav_workshop.js"
	env = Environment(loader=DictLoader({"templates/web.html":"{% block style %}{% endblock %}{% block page_content %}{% endblock %}","home.html":template_path.read_text()}),undefined=StrictUndefined,autoescape=True)
	home = env.get_template("home.html").render(**context)
	inputs = [template_path,page_path,Path(__file__),PREVIEW/"fixtures.json",PREVIEW/"adapter.js",PREVIEW/"vendor/jquery-3.7.1.min.js",*(ROOT/f"erpnext/svoenrav/{name}.py" for name in ("menu","flow","queue_rules","material_rules","cutting_rules"))]
	digest = hashlib.sha256()
	for path in inputs:
		digest.update(path.relative_to(ROOT).as_posix().encode());digest.update(b"\0");digest.update(path.read_bytes())
	payload = json.dumps(demo,ensure_ascii=False,separators=(",",":")).replace("<","\\u003c")
	vendor = escape_script((PREVIEW/"vendor/jquery-3.7.1.min.js").read_text())
	adapter = escape_script((PREVIEW/"adapter.js").read_text())
	page = escape_script(page_path.read_text())
	return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'">
<title>SVOENRAV — автономное превью</title><style>{BASE_CSS}</style></head>
<body><aside class="preview-banner"><strong>АВТОНОМНОЕ ПРЕВЬЮ · ВСЕ ДАННЫЕ ТЕСТОВЫЕ</strong>
<p>Главная страница построена из настоящего HTML-шаблона, рабочие экраны используют JavaScript проекта. Внешняя оболочка и элементы Frappe заменены тестовым адаптером. Это не запущенная ERP: права, база, складские движения, сохранение и проведение здесь не работают. Изменения пропадут после закрытия страницы.</p>
<div class="preview-toolbar"><button class="btn" id="preview-home-button">Главное меню</button><button class="btn" id="preview-workshop-button">Рабочие экраны</button><button class="btn btn-primary" id="preview-example-button">Пример раскроя</button></div><div id="preview-message" role="status"></div></aside>
<section class="preview-stage" id="preview-home">{home}</section>
<section class="preview-stage" id="preview-workshop" hidden><div id="preview-page-main"></div></section>
<section class="preview-stage" id="preview-document" hidden><div id="preview-document-body"></div></section>
<footer class="preview-footnote">Без подключения к серверу. SHA-256 исходников превью: <span id="preview-source-hash">{digest.hexdigest()}</span></footer>
<script type="application/json" id="preview-data">{payload}</script>
<script>{vendor}</script><script>window.SVOENRAV_DEMO=JSON.parse(document.getElementById("preview-data").textContent);</script>
<script>{adapter}</script><script>{page}</script><script>SVOENRAV_PREVIEW_START();</script>
</body></html>'''


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--check",action="store_true")
	args = parser.parse_args()
	content = render()
	if args.check:
		if not OUTPUT.exists() or OUTPUT.read_text() != content:
			raise SystemExit("Preview is stale. Run python tools/build_svoenrav_preview.py")
		print("Committed preview matches production template, JS and fixtures.")
	else:
		OUTPUT.write_text(content,encoding="utf-8")
		print(OUTPUT)


if __name__ == "__main__":
	main()
