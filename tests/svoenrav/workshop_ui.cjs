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
		if (method.endsWith("get_options")) return {operations, can_read_orders:true};
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
		finish({doctype:"Stock Entry",name:"new-stock-entry-1"});
		await Promise.all([first,second]);
		assert.equal(ui.page.prepare_button.prop("disabled"),false);
		assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.at(-1).args)),{operation:"manufacture",source_name:"WO-1",quantity:2});
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

		ui.page.options.operations=[];
		ui.dom.window.frappe.route_options={operation:"delete"};
		ui.page.apply_route();
		assert.equal(ui.page.operation_field.get_value(),"manufacture","Unknown route option must not choose another operation");
		console.log("Workshop DOM checks: operation controls, duplicate click, failure recovery, stale card responses, text escaping, safe links and route validation OK");
	} finally {
		ui.dom.window.close();
	}
})().catch((error)=>{console.error(error);process.exitCode=1;});
