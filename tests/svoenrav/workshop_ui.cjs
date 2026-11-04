// DOM behavior checks only. This does not replace real Frappe/browser acceptance.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const jquery = require("jquery");

const script = fs.readFileSync(path.join(__dirname, "../../erpnext/svoenrav/page/svoenrav_workshop/svoenrav_workshop.js"), "utf8");
const operations = [
	{key:"receipt", label:"Приход", source:"Purchase Order", target:"Purchase Receipt"},
	{key:"transfer", label:"Выдача", source:"Work Order", target:"Stock Entry"},
	{key:"manufacture", label:"Выпуск", source:"Work Order", target:"Stock Entry"},
	{key:"delivery", label:"Отгрузка", source:"Sales Order", target:"Delivery Note"},
];
const turn = () => new Promise(setImmediate);

async function setup() {
	const dom = new JSDOM("<!doctype html><html><body><div id='main'></div></body></html>", {url:"https://workshop.test/desk/svoenrav-workshop", runScripts:"outside-only"});
	const $ = jquery(dom.window);
	const calls = [];
	const routes = [];
	let handler = async (method) => {
		if (method.endsWith("get_options")) return {operations, can_read_orders:true, can_read_work_orders:true, can_cutting:true};
		throw new Error("Unexpected API: " + method);
	};
	dom.window.$ = $;
	dom.window.__ = (value) => value;
	dom.window.frappe = {
		pages:{"svoenrav-workshop":{}}, route_options:null,
		ui:{
			make_app_page:() => ({main:$("#main")}),
			form:{make_control:({parent,df}) => {
				const control = {df, value:null, $wrapper:$("<div class='form-group'></div>").appendTo(parent)};
				control.get_value = () => control.value;
				control.set_value = (value) => {
					const changed = value !== control.value;
					control.value = value;
					if (changed && df.onchange) df.onchange();
					return Promise.resolve();
				};
				return control;
			}},
		},
		xcall: (method,args) => {calls.push({method,args});return handler(method,args);},
		model:{sync:(doc) => [doc]},
		set_route:async (...args) => routes.push(args),
		msgprint:() => {},
	};
	dom.window.eval(script);
	const wrapper = {};
	dom.window.frappe.pages["svoenrav-workshop"].on_page_load(wrapper);
	await turn();
	return {dom, $, page:wrapper.svoenrav_workshop, calls, routes, setHandler:(value)=>{handler=value;}};
}

function card(name, text="Сумка") {
	const section = {allowed:true, rows:[], has_more:false};
	return {order:{name,customer_name:text,status:"To Deliver",currency:"RUB",grand_total:1000,advance_paid:0},url:"/desk/sales-order/"+name,items:[{item_name:text,qty:1,uom:"шт"}],production:section,stock:section,deliveries:section,invoices:section};
}

(async () => {
	const ui = await setup();
	try {
		assert.equal(ui.page.ready, true);
		assert.equal(ui.page.operation_field.get_value(), "receipt");
		assert.equal(ui.page.quantity_field.$wrapper.css("display"), "none");
		ui.page.operation_field.set_value("manufacture");
		assert.notEqual(ui.page.quantity_field.$wrapper.css("display"), "none");
		assert.equal(ui.page.source_field.df.options, "Work Order");
		ui.page.source_field.set_value("WO-1");
		ui.page.quantity_field.set_value(2);
		let finish;
		ui.setHandler(() => new Promise((resolve) => {finish=resolve;}));
		const first = ui.page.prepare();
		const second = ui.page.prepare();
		assert.equal(ui.calls.filter((row)=>row.method.endsWith("prepare_operation")).length,1,"Repeated click must not dispatch a second request");
		assert.equal(ui.page.prepare_button.prop("disabled"),true);
		finish({doctype:"Stock Entry",name:"new-stock-entry-1",docstatus:0,company:"TEST",items:[{item_name:"Кожа",qty:2,uom:"дм²",s_warehouse:"MAIN",t_warehouse:"WIP"}]});
		await Promise.all([first,second]);
		assert.equal(ui.page.prepare_button.prop("disabled"),false);
		assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1).args)),{operation:"manufacture",source_name:"WO-1",quantity:2});
		assert.equal(ui.routes.length,0,"Preparation must stop at the review screen");
		assert.match(ui.page.operation_review.text(),/Кожа/);
		ui.page.operation_review_controls.open.trigger("click");
		await turn();
		assert.equal(ui.routes.length,0,"Unchecked review must not open the document");
		ui.page.operation_review_controls.checkbox.prop("checked",true).trigger("change");
		ui.page.operation_review_controls.open.trigger("click");
		await turn();
		assert.equal(ui.routes[0][0],"Form");
		assert.equal(ui.routes[0][1],"Stock Entry");

		ui.setHandler(async()=>{throw new Error("Denied");});
		await ui.page.prepare();
		assert.equal(ui.page.preparing,false,"Failed requests must release the button");
		assert.equal(ui.page.prepare_button.prop("disabled"),false);

		const pending = {};
		ui.setHandler((method,args)=>new Promise((resolve)=>{pending[args.sales_order]=resolve;}));
		ui.page.order_field.set_value("SO-A");
		ui.page.order_field.set_value("SO-B");
		pending["SO-B"](card("SO-B","Новый заказ"));
		await turn();
		pending["SO-A"](card("SO-A","Устаревший заказ"));
		await turn();
		assert.match(ui.page.card.text(),/Новый заказ/);
		assert.doesNotMatch(ui.page.card.text(),/Устаревший заказ/);

		const malicious = card("SO-X","<img src=x onerror=alert(1)>");
		malicious.invoices={allowed:false,rows:[{name:"SECRET"}],has_more:false};
		ui.page.render_order(malicious);
		assert.equal(ui.page.card.find("img,script").length,0,"Document text must never be treated as HTML");
		assert.doesNotMatch(ui.page.card.text(),/SECRET/);
		assert.equal(ui.page.link({name:"bad",url:"javascript:alert(1)"}).hasAttribute("href"),false);
		assert.equal(ui.page.link({name:"bad",url:"https://evil.test/desk/order"}).hasAttribute("href"),false);
		assert.equal(ui.page.link({name:"ok",url:"/desk/sales-order/SO-1"}).hasAttribute("href"),true);

		const queue_pending = {};
		ui.setHandler((method,args)=>new Promise((resolve)=>{queue_pending[args.start]=resolve;}));
		const old_queue = ui.page.load_queue(0);
		const new_queue = ui.page.load_queue(50);
		queue_pending[50]({start:50,total:60,has_more:false,can_configure:false,rows:[{name:"WO-NEW",url:"/desk/work-order/WO-NEW",priority:1,item_name:"Новая очередь",qty:1,planning_paused:true,reason:"<img src=x onerror=alert(1)>"}]});
		await new_queue;
		queue_pending[0]({start:0,total:60,has_more:true,can_configure:true,settings_url:"/desk/private-settings",rows:[{name:"OLD",url:"/desk/work-order/OLD",qty:1,item_name:"Устаревшая очередь"}]});
		await old_queue;
		assert.match(ui.page.queue_body.text(),/Новая очередь/);
		assert.match(ui.page.queue_body.text(),/Пауза планирования/);
		assert.doesNotMatch(ui.page.queue_body.text(),/Устаревшая очередь/);
		assert.equal(ui.page.queue_body.find("img").length,0);
		assert.equal(ui.page.queue_settings.find("a").length,0);

		const handlers = {};
		ui.dom.window.frappe.ui.form.on = (name,events)=>{handlers[name]=events;};
		ui.dom.window.eval(fs.readFileSync(path.join(__dirname,"../../erpnext/svoenrav/doctype/svoenrav_settings/svoenrav_settings.js"),"utf8"));
		const buttons = {};
		const frm = {perm:[{write:1}],rows:[{label:"Старое"}],dirty_count:0,
			add_custom_button:(label,callback)=>{buttons[label]=callback;},
			clear_table:()=>{frm.rows=[];},add_child:(field,row)=>frm.rows.push(row),
			set_value:async(field,value)=>{frm[field]=value;},refresh_field:()=>{},dirty:()=>{frm.dirty_count++;}};
		handlers["SVOENRAV Settings"].refresh(frm);
		ui.dom.window.frappe.confirm=()=>{};
		buttons["Перенести сохранённое меню в таблицу"]();
		assert.equal(frm.rows[0].label,"Старое","Cancelled confirmation must preserve unsaved rows");
		ui.dom.window.frappe.confirm=(message,callback)=>callback();
		let finish_copy;
		ui.setHandler(()=>new Promise((resolve)=>{finish_copy=resolve;}));
		const copy_count=ui.calls.length;
		const copying=buttons["Перенести сохранённое меню в таблицу"]();
		await buttons["Заполнить стандартным меню"]();
		assert.equal(ui.calls.length,copy_count+1,"Two copies must not race");
		assert.equal(frm.rows[0].label,"Старое","Rows must survive until a successful response");
		finish_copy([{label:"Новое",enabled:1}]);
		await copying;
		assert.equal(frm.rows[0].label,"Новое");
		assert.equal(frm.menu_source,"Таблица");
		assert.equal(frm.dirty_count,1);
		assert.equal(frm.__sv_copying,false);
		ui.setHandler(async()=>{throw new Error("Denied");});
		await assert.rejects(buttons["Заполнить стандартным меню"]());
		assert.equal(frm.rows[0].label,"Новое","A failed copy must preserve table contents");
		assert.equal(frm.__sv_copying,false);
		ui.dom.window.locals={"SVOENRAV Menu Action":{"ROW":{guided_operation:"Выпуск"}}};
		let automatic_fields;
		ui.dom.window.frappe.model.set_value=async(cdt,cdn,fields)=>{automatic_fields=fields;};
		await handlers["SVOENRAV Menu Action"].guided_operation(frm,"SVOENRAV Menu Action","ROW");
		assert.equal(automatic_fields.action_doctype,"Stock Entry");
		assert.equal(automatic_fields.open_mode,"Новый документ");

		const material_pending = {};
		ui.setHandler((method,args)=>new Promise((resolve)=>{material_pending[args.work_order]=resolve;}));
		ui.page.open_materials("WO-A");
		ui.page.open_materials("WO-B");
		const report = (name,label,shortage) => ({work_order:name,url:"/desk/work-order/"+name,checked_at:"2026-11-04 12:00",status:"shortage",notice:"Не создаёт резерв",rows:[{item_name:label,stock_uom:"дм²",warehouse:"MAIN",required:10,transferred:0,pending:10,actual:0,reserved_total:0,own_reserved:0,free:0,shortage,status:"shortage"}]});
		material_pending["WO-B"](report("WO-B","<img src=x onerror=alert(1)>",null));
		await turn();
		material_pending["WO-A"](report("WO-A","Устаревшие материалы",10));
		await turn();
		assert.doesNotMatch(ui.page.material_body.text(),/Устаревшие материалы/);
		assert.equal(ui.page.material_body.find("img").length,0);
		assert.match(ui.page.material_body.text(),/Не создаёт резерв/);
		const cells=ui.page.material_body.find("tbody tr:first td");
		assert.equal(cells.eq(4).text(),"0","A real zero must be visible as zero");
		assert.equal(cells.eq(8).text(),"—","Unknown shortage must not become zero");
		ui.setHandler(async()=>{throw new Error("Forbidden");});
		await ui.page.load_materials();
		assert.match(ui.page.material_body.text(),/Проверка не выполнена/);
		assert.equal(ui.page.material_body.find("table").length,0,"An error must not leave an old successful report visible");

		ui.page.source_field.set_value("WO-STALE");
		let finish_review;
		ui.setHandler(()=>new Promise((resolve)=>{finish_review=resolve;}));
		const stale_review=ui.page.prepare();
		ui.page.quantity_field.set_value(3);
		finish_review({doctype:"Stock Entry",name:"new-old",docstatus:0,items:[]});
		await stale_review;
		assert.equal(ui.page.operation_review.children().length,0,"Changing inputs must discard an old prepared document");
		assert.equal(ui.page.operation_review_controls,null);

		const cutting={work_order:"WO-1",material:"LEATHER",area_unit:"дм²",input_area:20,used_area:12,reusable_area:6,waste_area:2,notes:""};
		for(const[key,value]of Object.entries(cutting))await ui.page.cutting_fields[key].set_value(value);
		ui.setHandler(async()=>({document:{...cutting,doctype:"SVOENRAV Cutting Draft",name:"new-cut",docstatus:0,company:"TEST",yield_percent:60},posted:false}));
		await ui.page.evaluate_cutting();
		assert.match(ui.page.cutting_review.text(),/без складских движений/);
		assert.match(ui.page.cutting_review.text(),/60%/);
		ui.page.cutting_fields.used_area.set_value(13);
		assert.equal(ui.page.cutting_review.children().length,0,"Editing a cutting quantity must clear the previous check");

		ui.page.source_field.set_value("WO-1");ui.page.quantity_field.set_value(1);
		ui.setHandler(async()=>({existing_drafts:{allowed:true,rows:[{name:"SE-DRAFT",url:"/desk/stock-entry/SE-DRAFT",modified:"2026-11-04"}],has_more:false}}));
		await ui.page.prepare();
		assert.match(ui.page.operation_review.text(),/SE-DRAFT/);
		assert.equal(ui.page.operation_review_controls,null,"Existing draft must not leave a previously prepared new document openable");

		const steps=card("SO-STEPS");steps.order.docstatus=1;steps.order.per_delivered=20;
		steps.production={allowed:true,has_more:false,rows:[{name:"WO-STEPS",item_name:"Тест",docstatus:1,status:"In Process",qty:5,produced_qty:1,url:"/desk/work-order/WO-STEPS"}]};
		ui.page.render_order(steps);
		ui.page.card.find("button").filter((_,el)=>el.textContent === "Выдача").trigger("click");await turn();
		assert.equal(ui.page.source_field.get_value(),"WO-STEPS","Order actions must prefill the exact source, not a similar item");
		assert.equal(ui.page.operation_field.get_value(),"transfer");
		ui.page.simple_button.trigger("click");
		assert.equal(ui.page.root.hasClass("sv-simple"),true);
		assert.equal(ui.page.card.find(".sv-finance").first().css("display"),"none");
		assert.equal(ui.page.options.operations.length,4,"Simple mode is presentation, not a change in permissions");
		ui.page.simple_button.trigger("click");

		const plans=[];ui.setHandler(()=>new Promise(resolve=>plans.push(resolve)));
		const planA=ui.page.load_plan(),planB=ui.page.load_plan();
		plans[1]({complete:false,checked_at:"NEW",scope:"Неполно",orders:[{work_order:"WO-NEW",status:"unknown",rows:[]}]});await planB;
		plans[0]({complete:true,checked_at:"OLD",scope:"Устарело",orders:[]});await planA;
		assert.match(ui.page.plan_body.text(),/WO-NEW/);assert.doesNotMatch(ui.page.plan_body.text(),/Устарело/);

		const histories=[];ui.setHandler(()=>new Promise(resolve=>histories.push(resolve)));
		const hA=ui.page.load_history("SO-STEPS"),hB=ui.page.load_history("SO-STEPS");
		histories[1]({allowed:false,rows:[{name:"SECRET"}],partial:true,notice:"Нет доступа"});await hB;
		histories[0]({allowed:true,rows:[],partial:false,notice:"OLD HISTORY"});await hA;
		assert.match(ui.page.history_body.text(),/Нет доступа/);assert.doesNotMatch(ui.page.history_body.text(),/SECRET|OLD HISTORY/);

		let finishSpec;
		ui.setHandler((method,args)=>method.endsWith("get_specification") ? new Promise(resolve=>{finishSpec=resolve;}) : Promise.resolve(report(args.work_order,"Материал",0)));
		ui.page.material_field.set_value("WO-1");await turn();
		const staleSpec=ui.page.load_specification();
		ui.page.material_field.set_value("WO-2");
		finishSpec({state:"matches",payload:"OLD SPEC"});await staleSpec;
		assert.doesNotMatch(ui.page.spec_body.text(),/OLD SPEC/);
		ui.setHandler(async(method)=>method.endsWith("capture_specification") ? {state:"matches",payload:"CAPTURED",notice:"Без списания"} : {state:"missing",can_capture:true});
		await ui.page.load_specification();
		ui.page.spec_body.find("button").trigger("click");await turn();
		assert.match(ui.page.spec_body.text(),/CAPTURED/);

		ui.page.options.operations=[];
		ui.dom.window.frappe.route_options={operation:"delete"};
		ui.page.apply_route();
		assert.equal(ui.page.operation_field.get_value(),"transfer","Unknown route option must not choose another operation");
		console.log("Workshop DOM checks: operation controls, duplicate click, failure recovery, stale card responses, text escaping, safe links, route validation, queue races, menu editor preservation and material report races/unknown values OK");
	} finally {
		ui.dom.window.close();
	}
})().catch((error)=>{console.error(error);process.exitCode=1;});
