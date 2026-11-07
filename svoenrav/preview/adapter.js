/* Preview-only adapter. No server connection, persistence or real Frappe forms. */
(() => {
	"use strict";
	const demo = window.SVOENRAV_DEMO;
	const clone = (value) => JSON.parse(JSON.stringify(value));
	const docs = new Map();
	let sequence = 0;
	let modelVersion = 0;
	let snapshotCaptured = true;
	const message = (text) => { document.getElementById("preview-message").textContent = String(text); };
	const show = (view) => {
		for (const name of ["home", "workshop", "document"]) document.getElementById("preview-" + name).hidden = name !== view;
		message("");
		window.scrollTo(0, 0);
	};
	const current = () => window.SVOENRAV_PREVIEW_PAGE;
	const control = ({parent, df}) => {
		const wrapper = $("<div class='form-group'></div>").appendTo(parent);
		$("<label></label>").text(df.label + (df.reqd ? " *" : "")).appendTo(wrapper);
		let input;
		if (df.fieldtype === "Select") {
			input = $("<select></select>");
			const options = typeof df.options === "string" ? df.options.split("\n") : df.options;
			for (const option of options || []) {
				const value = typeof option === "object" ? option.value : option;
				$("<option></option>").val(value).text(typeof option === "object" ? option.label : option || "Выберите…").appendTo(input);
			}
		} else if (df.fieldtype === "Small Text") input = $("<textarea rows='2'></textarea>");
		else {
			input = $("<input>").attr("type", df.fieldtype === "Float" ? "number" : "text");
			if (df.fieldtype === "Float") input.attr("step", "any");
			if (df.fieldtype === "Link") {
				const id = "demo-options-" + (++sequence);
				input.attr("list", id);
				const list = $("<datalist></datalist>").attr("id", id).appendTo(wrapper);
				const values = {"Work Order":[demo.work_order.name,demo.second_work_order.name],"Sales Order":[demo.sales_order.name],"Purchase Order":[demo.purchase_order],"Item":[demo.material,demo.work_order.production_item],"UOM":["шт"],"Item Group":["Демо-изделия"]};
				for (const value of values[df.options] || []) $("<option></option>").val(value).appendTo(list);
			}
		}
		input.attr("name", df.fieldname).appendTo(wrapper);
		if (df.default != null) input.val(String(df.default));
		if (df.description) $("<small></small>").text(df.description).appendTo(wrapper);
		const result = {df, $wrapper:wrapper, $input:input, get_value:()=>input.val(), set_value:async(value)=>{
			const next = value == null ? "" : String(value);
			if (input.val() !== next) { input.val(next); if (df.onchange) df.onchange(); }
		}};
		input.on("input change",()=>{ if(df.onchange)df.onchange(); });
		return result;
	};

	// Exact 6-place arithmetic for the offline adapter. Checked against Python cases.
	function area_units(value) {
		if (value == null || typeof value === "boolean") throw Error("Заполните все площади.");
		const text = String(value).trim();
		const match = text.match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
		if (!match || text.length > 100) throw Error("Площадь должна быть числом.");
		let digits = BigInt(match[2] + (match[3] || ""));
		if (digits === 0n) return 0n;
		if (match[1] === "-") throw Error("Площадь не может быть отрицательной.");
		const power = Number(match[4] || 0) - (match[3] || "").length + 6;
		if (!Number.isSafeInteger(power) || Math.abs(power) > 100) throw Error("Площадь вне диапазона.");
		if (power < 0) {
			const divisor = 10n ** BigInt(-power);
			if (digits % divisor) throw Error("Для площади допустимо не более шести знаков после запятой.");
			digits /= divisor;
		} else digits *= 10n ** BigInt(power);
		if (digits > 1000000000000000n) throw Error("Площадь вне диапазона.");
		return digits;
	}
	function calculate_cutting(args) {
		if (!["дм²","м²","см²"].includes(args.area_unit)) throw Error("Выберите единую единицу площади.");
		const keys=["input_area","used_area","reusable_area","waste_area"];
		const values=keys.map((key)=>area_units(args[key]));
		if (values[0] <= 0n || values[1]+values[2]+values[3] !== values[0]) throw Error("Баланс не сходится: детали + пригодный остаток + отходы должны равняться исходной площади.");
		const report={area_unit:args.area_unit,balanced:true};
		keys.forEach((key,index)=>{report[key]=Number(values[index])/1000000;});
		report.consumed_area=Number(values[1]+values[3])/1000000;
		const numerator=values[1]*1000000n;
		report.yield_percent=Number((2n*numerator+values[0])/(2n*values[0]))/10000;
		return report;
	}
	window.SVOENRAV_PREVIEW_CALCULATE_CUTTING=calculate_cutting;

	const prepared = (args) => {
		const spec = demo.operations.find((row)=>row.key===args.operation);
		if (!spec) throw Error("Неизвестная операция.");
		const source = spec.source === "Work Order" ? demo.work_order.name : spec.source === "Sales Order" ? demo.sales_order.name : demo.purchase_order;
		if (args.source_name !== source) throw Error("В превью доступен только тестовый документ " + source);
		const doc={doctype:spec.target,name:"new-demo-document-"+(++sequence),docstatus:0,__islocal:1,company:demo.company,items:[]};
		if (spec.source === "Work Order") {
			const qty=Number(args.quantity);
			const max=spec.key==="transfer" ? demo.work_order.qty-demo.work_order.material_transferred_for_manufacturing : demo.work_order.material_transferred_for_manufacturing-demo.work_order.produced_qty;
			if(!Number.isFinite(qty)||qty<=0||qty>max)throw Error("В тестовом задании доступно количество не более " + max);
			doc.work_order=source;
			doc.items.push({item_code:demo.material,item_name:demo.material_name,qty:qty*10,uom:"дм²",s_warehouse:spec.key==="transfer"?demo.warehouse:demo.wip_warehouse,t_warehouse:spec.key==="transfer"?demo.wip_warehouse:null});
			if(spec.key==="manufacture")doc.items.push({item_code:demo.work_order.production_item,item_name:demo.work_order.item_name,qty,uom:"шт",t_warehouse:demo.fg_warehouse});
		} else doc.items.push(spec.key==="receipt"?{item_code:demo.material,item_name:demo.material_name,qty:60,uom:"дм²",warehouse:demo.warehouse}:{item_code:demo.work_order.production_item,item_name:demo.work_order.item_name,qty:4,uom:"шт",warehouse:demo.fg_warehouse});
		return doc;
	};
	const xcall=async(method,args={})=>{
		try {
			if(method.endsWith("get_options"))return {operations:clone(demo.operations),can_read_orders:true,can_read_work_orders:true,can_cutting:true,can_reserve:true,can_allocate_payments:true,can_catalog:true,can_create_model:true,can_create_item:true,can_units:true};
			if(method.endsWith("prepare_operation")) {
				if(args.operation === "delivery" && args.source_name === demo.sales_order.name) return {existing_drafts:{allowed:true,rows:[{name:"DEMO-DN-DRAFT",url:"/desk/delivery-note/DEMO-DN-DRAFT",modified:"2026-11-04 11:00:00"}],has_more:false}};
				return prepared(args);
			}
			if(method.endsWith("get_models")) {
				const query=(args.search||"").toLowerCase();const rows=demo.models.filter(row=>(args.state==="all"||!!row.archived===(args.state==="archived")) && [row.title,row.model_code,row.item_code].some(value=>value.toLowerCase().includes(query)));
				return {rows:clone(rows.slice(args.start||0,(args.start||0)+24)),start:Number(args.start||0),has_more:rows.length>(args.start||0)+24,can_create:true};
			}
			if(method.endsWith("get_model")) {
				const model=demo.models.find(row=>row.name===args.model);if(!model)throw Error("Демо-модель не найдена.");return clone(model);
			}
			if(method.endsWith("create_model")) {
				if(!args.code || !args.title || demo.models.some(row=>row.name===args.code))throw Error("Укажите уникальный артикул и название.");
				if(!args.item_code && (!args.stock_uom || !args.item_group))throw Error("Укажите номенклатуру либо её единицу и группу.");
				const row={name:args.code,model_code:args.code,title:args.title,item_code:args.item_code||args.code,description:args.description||"",stock_uom:args.stock_uom||"шт",item_group:args.item_group||"Демо-изделия",archived:0,numbered:1,photos:[],main_photo:null,can_edit:true,modified:"DEMO-"+(++modelVersion),url:"/desk/svoenrav-model/"+encodeURIComponent(args.code)};demo.models.push(row);return clone(row);
			}
			if(method.endsWith("update_model") || method.endsWith("set_cover") || method.endsWith("remove_photo")) {
				const row=demo.models.find(row=>row.name===args.model);if(!row)throw Error("Демо-модель не найдена.");
				if(args.modified!=null && args.modified!==row.modified)throw Error("Карточка изменена.");
				if(method.endsWith("update_model"))for(const key of ["title","description","archived"])if(args[key]!=null)row[key]=args[key];
				if(method.endsWith("set_cover")){if(!row.photos.some(p=>p.url===args.file_url))throw Error("Фото не найдено.");row.main_photo=args.file_url;}
				if(method.endsWith("remove_photo")){row.photos=row.photos.filter(p=>p.url!==args.file_url);if(row.main_photo===args.file_url)row.main_photo=row.photos[0]?.url||null;}
				row.modified="DEMO-"+(++modelVersion);return clone(row);
			}
			if(method.endsWith("get_units")) {
				const query=(args.search||"").toLowerCase();const rows=demo.units.filter(row=>(!args.model||row.model===args.model) && [row.name,row.model_title,row.item_code].some(value=>value.toLowerCase().includes(query)));return {rows:clone(rows),start:0,has_more:false,notice:"Тестовый реестр: один выпуск действующий, другой отменён; номера различаются и сохраняются."};
			}
			if(method.endsWith("get_unit")){const row=demo.units.find(row=>row.name===args.number);if(!row)throw Error("Тестовый номер не найден.");return clone(row);}
			if(method.endsWith("numbering_state"))return {enabled:true,can_configure:true,next_number:3,last_issued:2,url:"/desk/svoenrav-product-sequence/main",notice:"Вымышленная последовательность настроена только для демонстрации. Рабочий стартовый номер нужно подтвердить отдельно."};
			if(method.endsWith("get_queue_plan"))return clone(demo.plan);
			if(method.endsWith("reserve_queue")) {
				const created=[];
				for(const order of demo.plan.orders) for(const row of order.rows) if(row.planned_free > 0) {
					created.push({name:"DEMO-RESERVE-"+(++sequence),url:"/desk/stock-reservation-entry/DEMO-RESERVE"});
					row.own_reserved += row.planned_free; row.planned_free=0;
				}
				return {created,count:created.length,notice:"Только имитация в памяти страницы. Реальные резервы не создаются."};
			}
			if(method.endsWith("get_order_history"))return clone(demo.history);
			if(method.endsWith("get_specification") || method.endsWith("capture_specification")) {
				if(args.work_order !== demo.work_order.name) throw Error("Снимок в превью подготовлен только для " + demo.work_order.name);
				if(method.endsWith("capture_specification"))snapshotCaptured = true;
				return snapshotCaptured ? clone(demo.specification) : {state:"missing",can_capture:true};
			}
			if(method.endsWith("get_order_card")){
				if(args.sales_order!==demo.sales_order.name)throw Error("В превью доступен только " + demo.sales_order.name);
				return clone(demo.order_card);
			}
			if(method.endsWith("get_production_queue"))return {rows:args.start?[]:clone(demo.queue_rows),start:Number(args.start||0),has_more:false,total:2,can_configure:false};
			if(method.endsWith("get_material_coverage")){
				if(args.work_order === demo.second_work_order.name)return clone(demo.coverage2);
				if(args.work_order!==demo.work_order.name)throw Error("Выберите тестовое задание.");
				return clone(demo.coverage);
			}
			if(method.endsWith("evaluate_cutting")){
				if(args.work_order!==demo.work_order.name||args.material!==demo.material)throw Error("Выберите тестовое задание и материал из примера.");
				const summary=calculate_cutting(args);
				return {summary,posted:false,document:{...clone(args),...summary,doctype:"SVOENRAV Cutting Draft",name:"new-demo-cutting-"+(++sequence),docstatus:0,__islocal:1,company:demo.company}};
			}
			throw Error("Этот серверный метод в автономном превью не эмулируется.");
		} catch(error) {message(error.message);throw error;}
	};
	window.__=(value)=>value;
	window.frappe={pages:{"svoenrav-workshop":{}},route_options:null,ui:{make_app_page:()=>({main:$("#preview-page-main")}),form:{make_control:control},FileUploader:function(){message("В автономном превью файлы не загружаются. В ERP откроется загрузчик закрытых фотографий модели.");}},xcall,msgprint:message,confirm:(text,callback)=>{if(window.confirm(text))callback();},
		model:{sync:(doc)=>{docs.set(doc.name,clone(doc));return [doc];}},
		set_route:async(view,doctype,name)=>{
			if(view!=="Form")throw Error("В превью доступен только просмотр документа.");
			show("document");
			const target=$("#preview-document-body").empty();
			$("<h2></h2>").text("Тестовый переход в документ: " + doctype).appendTo(target);
			$("<p></p>").text("Реальная стандартная форма Frappe здесь не запущена. Ниже — данные, которые переданы из настоящего экрана проверки. Сохранение и проведение отключены.").appendTo(target);
			const doc=docs.get(name);
			const pre=$("<pre></pre>").text(JSON.stringify(doc,null,2)).appendTo(target);
			pre.attr("aria-label","Тестовые данные документа");
		},
	};
	window.fetch=()=>Promise.reject(Error("Сетевые запросы отключены в автономном превью."));
	window.XMLHttpRequest=function(){throw Error("Сетевые запросы отключены в автономном превью.");};
	window.SVOENRAV_PREVIEW_START=()=>{
		const wrapper={};
		frappe.pages["svoenrav-workshop"].on_page_load(wrapper);
		window.SVOENRAV_PREVIEW_PAGE=wrapper.svoenrav_workshop;
		document.getElementById("preview-home-button").onclick=()=>show("home");
		document.getElementById("preview-workshop-button").onclick=()=>show("workshop");
		document.getElementById("preview-order-button").onclick=async()=>{show("workshop");const page=current();page.show("order");await page.order_field.set_value(demo.sales_order.name);};
		document.getElementById("preview-example-button").onclick=async()=>{
			show("workshop");const page=current();page.show("cutting");
			for(const[key,value]of Object.entries(demo.cutting))await page.cutting_fields[key].set_value(value);
		};
		document.addEventListener("click",(event)=>{
			const anchor=event.target.closest("a");if(!anchor)return;
			const href=anchor.getAttribute("href")||"";
			if(href.startsWith("#"))return;
			event.preventDefault();
			const url=new URL(href,window.location.href);
			if(url.pathname==="/desk/svoenrav-workshop"){
				show("workshop");frappe.route_options=Object.fromEntries(url.searchParams);current().apply_route();
			} else message("Этот переход ведёт в штатную форму ERPNext. В автономном превью она не запущена.");
		});
		show("home");
	};
})();
