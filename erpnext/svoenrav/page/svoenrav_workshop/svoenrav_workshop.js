// Copyright (c) 2026, SVOENRAV
// License: GNU General Public License v3. See license.txt

frappe.pages["svoenrav-workshop"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Мастерская SVOENRAV",
		single_column: true,
	});
	wrapper.svoenrav_workshop = new SvoenravWorkshop(page);
};

frappe.pages["svoenrav-workshop"].on_page_show = function (wrapper) {
	if (wrapper.svoenrav_workshop) wrapper.svoenrav_workshop.apply_route();
};

class SvoenravWorkshop {
	constructor(page) {
		this.page = page;
		this.request_id = 0;
		this.queue_request_id = 0;
		this.material_request_id = 0;
		this.history_request_id = 0;
		this.plan_request_id = 0;
		this.spec_request_id = 0;
		this.operation_revision = 0;
		this.cutting_revision = 0;
		this.ready = false;
		this.root = $("<div class='sv-workshop'></div>").appendTo(page.main);
		this.root.append(`<style>
		.sv-workshop{padding:20px;max-width:1200px;margin:auto}
		.sv-workshop h2{font-size:21px;margin:8px 0 16px}.sv-workshop h3{font-size:17px;margin:24px 0 12px}
		.sv-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
		.sv-workshop.sv-simple .sv-advanced,.sv-workshop.sv-simple .sv-finance{display:none!important}
		.sv-mobile-nav{display:none;width:100%;min-height:44px;padding:10px;border:1px solid var(--border-color,#dce4df);border-radius:8px;margin-bottom:12px;font:inherit}
		.sv-workshop button{min-height:44px}.sv-tabs button{min-height:44px}.sv-panel{padding:20px;border:1px solid var(--border-color,#dce4df);border-radius:10px;margin-bottom:18px}
		.sv-controls{display:grid;grid-template-columns:1fr 1fr;gap:18px}.sv-quantity{max-width:260px}
		.sv-help{line-height:1.6;color:var(--text-muted,#647168);font-size:13px;white-space:pre-line}
		.sv-review{min-height:44px;margin-top:12px}.sv-summary{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}
		.sv-summary>div{padding:12px 16px;border:1px solid var(--border-color,#dce4df);border-radius:8px}
		.sv-summary strong{display:block;margin-top:4px}.sv-table-wrap{overflow:auto}
		.sv-workshop table{width:100%;font-size:13px}.sv-workshop td,.sv-workshop th{padding:10px;border-bottom:1px solid var(--border-color,#dce4df);vertical-align:top}
		.sv-workshop a{overflow-wrap:anywhere}.sv-feedback:empty{display:none}.sv-feedback{margin:12px 0}
		@media(max-width:600px){.sv-mobile-nav{display:block}.sv-workshop>.sv-tabs>button:not(.sv-mode){display:none}.sv-workshop{padding:12px}.sv-panel{padding:14px}.sv-controls{grid-template-columns:1fr;gap:0}.sv-summary>div{flex:1 1 42%}.sv-workshop td,.sv-workshop th{padding:8px}}
		</style>`);
		this.mobile_nav = $("<select class='sv-mobile-nav' aria-label='Раздел мастерской'></select>").appendTo(this.root).on("change", () => this.show(this.mobile_nav.val()));
		for(const [value,label] of [["operations","Операции"],["order","Карточка заказа"],["queue","Очередь производства"],["materials","Материалы задания"],["cutting","Раскрой"],["plan","План материалов"],["policy","Учёт материалов"]]) $("<option></option>").val(value).text(label).appendTo(this.mobile_nav);
		this.tabs = $("<nav class='sv-tabs' aria-label='Разделы мастерской'></nav>").appendTo(this.root);
		this.simple_button = $("<button class='btn btn-default sv-mode' type='button' aria-pressed='false'>Режим сотрудника</button>").appendTo(this.tabs).on("click", () => {
			this.simple_mode = !this.simple_mode;
			this.root.toggleClass("sv-simple", this.simple_mode);
			this.mobile_nav.find("option[value=plan]").prop("hidden",!!this.simple_mode);
			if(this.simple_mode && this.current_view === "plan") this.show("queue");
			this.simple_button.attr("aria-pressed", String(this.simple_mode)).text(this.simple_mode ? "Полный экран" : "Режим сотрудника");
		});
		this.plan_tab = $("<button class='btn btn-default sv-advanced' type='button'>План материалов</button>").appendTo(this.tabs).on("click", () => this.show("plan"));
		this.operation_tab = $("<button class='btn btn-default' type='button'>Операции</button>").appendTo(this.tabs).on("click", () => this.show("operations"));
		this.order_tab = $("<button class='btn btn-default' type='button'>Карточка заказа</button>").appendTo(this.tabs).on("click", () => this.show("order"));
		this.queue_tab = $("<button class='btn btn-default' type='button'>Очередь производства</button>").appendTo(this.tabs).on("click", () => this.show("queue"));
		this.material_tab = $("<button class='btn btn-default' type='button'>Материалы задания</button>").appendTo(this.tabs).on("click", () => this.show("materials"));
		this.cutting_tab = $("<button class='btn btn-default' type='button'>Раскрой</button>").appendTo(this.tabs).on("click", () => this.show("cutting"));
		this.policy_tab = $("<button class='btn btn-default' type='button'>Как учитываются материалы</button>").appendTo(this.tabs).on("click", () => this.show("policy"));
		this.feedback = $("<div class='sv-feedback text-muted' role='status'></div>").appendTo(this.root);
		this.operations_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.order_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.queue_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.material_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.cutting_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.plan_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.policy_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.build_policy();
		this.show("operations");
		this.load_options();
	}

	async load_options() {
		this.feedback.text("Проверяем доступные операции…");
		try {
			this.options = await frappe.xcall("erpnext.svoenrav.workshop.get_options");
			this.build_operations();
			this.build_order();
			this.build_queue();
			this.build_materials();
			this.build_cutting();
			this.build_plan();
			if(this.options.simple_default && !this.simple_mode) this.simple_button.trigger("click");
			this.ready = true;
			this.feedback.empty();
			this.apply_route();
		} catch (error) {
			this.feedback.text("Не удалось загрузить доступные операции. Обновите страницу или проверьте права доступа.");
		}
	}

	show(view) {
		this.current_view = view;
		this.mobile_nav.val(view);
		this.plan_panel.toggle(view === "plan");
		this.operations_panel.toggle(view === "operations");
		this.order_panel.toggle(view === "order");
		this.queue_panel.toggle(view === "queue");
		this.material_panel.toggle(view === "materials");
		this.cutting_panel.toggle(view === "cutting");
		this.policy_panel.toggle(view === "policy");
		for (const [key, button] of [["plan", this.plan_tab], ["operations", this.operation_tab], ["order", this.order_tab], ["queue", this.queue_tab], ["materials", this.material_tab], ["cutting", this.cutting_tab], ["policy", this.policy_tab]]) {
			button.toggleClass("btn-primary", key === view).attr("aria-pressed", String(key === view));
		}
		if (view === "queue" && this.ready && this.options.can_read_work_orders) this.load_queue(this.queue_start || 0);
	}

	apply_route() {
		if (!this.ready) return;
		const route = frappe.route_options || {};
		// Consume only our known options; never accept document fields or URLs.
		if (!["operation", "sales_order", "work_order", "view"].some((key) => key in route)) return;
		frappe.route_options = null;
		if (typeof route.work_order === "string" && this.material_field) return this.open_materials(route.work_order);
		if (route.view === "plan") return this.show("plan");
		if (route.view === "materials") return this.show("materials");
		if (route.view === "cutting") return this.show("cutting");
		if (route.view === "policy") return this.show("policy");
		if (route.view === "queue") return this.show("queue");
		if (typeof route.sales_order === "string" && this.order_field) {
			this.show("order");
			this.order_field.set_value(route.sales_order);
			return;
		}
		if (route.view === "order") return this.show("order");
		if (this.operation_field && this.options.operations.some((row) => row.key === route.operation)) {
			this.operation_field.set_value(route.operation);
			this.show("operations");
		}
	}

	build_operations() {
		this.operations_panel.append("<h2>Быстрые операции</h2>");
		if (!this.options.operations.length) {
			this.operations_panel.append($("<p></p>").text("Нет доступных операций. Проверьте права чтения исходных документов и создания целевых документов."));
			return;
		}
		const controls = $("<div class='sv-controls'></div>").appendTo(this.operations_panel);
		const operation_host = $("<div></div>").appendTo(controls);
		this.source_host = $("<div></div>").appendTo(controls);
		this.operation_field = frappe.ui.form.make_control({
			parent: operation_host,
			df: {
				fieldtype: "Select", label: "Операция", fieldname: "operation",
				options: this.options.operations.map((row) => ({value: row.key, label: row.label})),
				onchange: () => this.change_operation(),
			},
			render_input: true,
		});
		const qty_host = $("<div class='sv-quantity'></div>").appendTo(this.operations_panel);
		this.quantity_field = frappe.ui.form.make_control({
			parent: qty_host,
			df: {fieldtype: "Float", label: "Количество готовых изделий", fieldname: "quantity", description: "В единицах изделия из производственного задания; для передачи — на какое количество изделий выдаём материалы.", onchange: () => this.invalidate_review()},
			render_input: true,
		});
		this.operation_help = $("<p class='sv-help'></p>").appendTo(this.operations_panel);
		this.prepare_button = $("<button type='button' class='btn btn-primary sv-review'>Подготовить документ</button>")
			.appendTo(this.operations_panel).on("click", () => this.prepare());
		this.operation_review = $("<div aria-live='polite'></div>").appendTo(this.operations_panel);
		this.operation_field.set_value(this.options.operations[0].key);
		this.change_operation();
	}

	change_operation() {
		if (!this.quantity_field) return;
		this.invalidate_review();
		const spec = this.options.operations.find((row) => row.key === this.operation_field.get_value());
		if (!spec) return;
		this.source_host.empty();
		this.quantity_field.set_value(null);
		const is_production = spec.source === "Work Order";
		const labels = {"Purchase Order": "Заказ поставщику", "Work Order": "Производственное задание", "Sales Order": "Заказ покупателя"};
		this.source_field = frappe.ui.form.make_control({
			parent: this.source_host,
			df: {fieldtype: "Link", label: labels[spec.source], options: spec.source, fieldname: "source", reqd: 1, onchange: () => this.invalidate_review(), get_query: () => ({filters: {docstatus: 1, status: ["not in", ["Stopped", "Closed", "Completed", "Cancelled", "On Hold"]]}})},
			render_input: true,
		});
		this.quantity_field.$wrapper.toggle(is_production);
		this.operation_help.text(is_production
			? "Материалы и склады подставляются из задания. Перед сохранением проверьте фактический расход, пригодные остатки, партии и номера. Выдача — перемещение; расход отражается при выпуске. Повторное отдельное списание этих материалов не требуется."
			: "Позиции и оставшиеся количества подставляются из исходного заказа. В открывшемся документе оставьте фактически принятые или отгружаемые строки и уточните количества.");
		this.operation_help.append(document.createTextNode("\nПодготовленный документ нужно проверить, сохранить и провести в стандартной форме. Эта кнопка сама не проводит операцию. Перед подготовкой проверьте существующие черновики."));
	}

	async prepare() {
		if (this.preparing) return;
		const spec = this.options.operations.find((row) => row.key === this.operation_field.get_value());
		const source = this.source_field.get_value();
		if (!source) return frappe.msgprint("Выберите исходный документ.");
		const args = {operation: spec.key, source_name: source};
		if (spec.source === "Work Order") {
			args.quantity = this.quantity_field.get_value();
			if (!Number.isFinite(Number(args.quantity)) || Number(args.quantity) <= 0) return frappe.msgprint("Укажите количество больше нуля.");
		}
		this.preparing = true;
		this.feedback.empty();
		this.prepare_button.prop("disabled", true);
		this.operation_review.empty();
		this.operation_review_controls = null;
		const revision = this.operation_revision;
		try {
			const doc = await frappe.xcall("erpnext.svoenrav.workshop.prepare_operation", args);
			if (revision !== this.operation_revision) return;
			if (doc.existing_drafts) {
				this.render_drafts(doc.existing_drafts);
				return;
			}
			this.operation_review_controls = this.render_review(this.operation_review, doc, spec, () => revision === this.operation_revision, source);
		} catch (error) {
			this.feedback.text("Документ не подготовлен. Проверьте сообщение ERPNext и исходные данные.");
		} finally {
			this.preparing = false;
			this.prepare_button.prop("disabled", false);
		}
	}

	async open_operation(key, source) {
		if (!this.operation_field || !this.options.operations.some(row => row.key === key)) return;
		const request = this.action_request_id = (this.action_request_id || 0) + 1;
		await this.operation_field.set_value(key);
		if(request !== this.action_request_id) return;
		this.change_operation();
		await this.source_field.set_value(source);
		if(request === this.action_request_id) this.show("operations");
	}

	render_drafts(section) {
		$("<h3>Уже есть черновики</h3>").appendTo(this.operation_review);
		$("<p></p>").text("Откройте существующий документ и проверьте его. Новый документ короткая форма не подготовила. После обработки черновика повторите проверку.").appendTo(this.operation_review);
		this.table(this.operation_review, ["Документ", "Изменён"], section.rows.map(row => [this.link(row), row.modified]));
		if (section.has_more) $("<p></p>").text("Есть другие черновики. Проверьте полный список ERPNext.").appendTo(this.operation_review);
	}

	invalidate_review() {
		this.operation_revision++;
		if (this.operation_review) this.operation_review.empty();
		this.operation_review_controls = null;
	}

	render_review(host, doc, spec, is_current, source) {
		if (doc.doctype !== spec.target || doc.docstatus !== 0) throw new Error("Ожидался новый документ нужного типа");
		host.empty();
		$("<h3></h3>").text("Проверка: " + spec.label).appendTo(host);
		$("<p></p>").text("Источник: " + source + " · Компания: " + (doc.company || "не задана")).appendTo(host);
		if (spec.key === "cutting") {
			this.table(host, ["Часть раскроя", "Площадь", "Единица"], [
				["Исходный материал", doc.input_area, doc.area_unit], ["Детали", doc.used_area, doc.area_unit],
				["Пригодный остаток", doc.reusable_area, doc.area_unit], ["Отходы", doc.waste_area, doc.area_unit],
			]);
			$("<p class='sv-help'></p>").text(`Баланс сходится. Выход деталей: ${doc.yield_percent}%. Карточка не создаёт складских движений и проводок.`).appendTo(host);
		} else {
			this.table(host, ["Позиция", "Количество", "Единица", "Откуда", "Куда"], (doc.items || []).map((row) => [
				row.item_name || row.item_code, row.qty, row.uom || row.stock_uom,
				row.s_warehouse || doc.from_warehouse || (spec.key === "delivery" ? row.warehouse : null),
				row.t_warehouse || doc.to_warehouse || (spec.key === "receipt" ? row.warehouse : null),
			]));
			$("<p class='sv-help'></p>").text("Это предварительная проверка. Количества строк, склады, партии и фактический расход можно уточнить в стандартном документе. Сохранение и проведение выполняются отдельно в ERPNext.").appendTo(host);
		}
		const label = $("<label style='display:block;margin-top:16px'></label>").appendTo(host);
		const checkbox = $("<input type='checkbox'>").appendTo(label);
		label.append(document.createTextNode(" Проверил данные подготовленного документа"));
		const open = $("<button type='button' class='btn btn-primary sv-review' disabled>Открыть документ ERPNext</button>").appendTo(host);
		checkbox.on("change", () => open.prop("disabled", !checkbox.prop("checked")));
		open.on("click", async () => {
			if (!checkbox.prop("checked") || !is_current()) return;
			open.prop("disabled", true);
			try {
				const docs = frappe.model.sync(doc);
				await frappe.set_route("Form", docs[0].doctype, docs[0].name);
			} finally {
				open.prop("disabled", false);
			}
		});
		return {checkbox, open};
	}

	build_cutting() {
		this.cutting_panel.append("<h2>Карточка фактического раскроя</h2>");
		$("<p class='sv-help'></p>").text("Учёт измерений: исходная площадь = детали + пригодный остаток + отходы. Это карточка без автоматического списания кожи и возврата на склад. Все площади вводятся в одной выбранной единице.").appendTo(this.cutting_panel);
		if (!this.options.can_cutting) {
			this.cutting_panel.append($("<p></p>").text("Требуются права чтения задания и материала и создания карточки раскроя."));
			return;
		}
		this.cutting_fields = {};
		const controls = $("<div class='sv-controls'></div>").appendTo(this.cutting_panel);
		const definitions = [
			{fieldname:"work_order",label:"Производственное задание",fieldtype:"Link",options:"Work Order",reqd:1},
			{fieldname:"material",label:"Материал из задания",fieldtype:"Link",options:"Item",reqd:1},
			{fieldname:"skin_reference",label:"Метка шкуры / куска",fieldtype:"Data"},
			{fieldname:"area_unit",label:"Единица площади",fieldtype:"Select",options:"\nдм²\nм²\nсм²",reqd:1},
			{fieldname:"input_area",label:"Исходная площадь",fieldtype:"Float",precision:6,reqd:1},
			{fieldname:"used_area",label:"Площадь деталей",fieldtype:"Float",precision:6,reqd:1,default:0},
			{fieldname:"reusable_area",label:"Пригодный остаток",fieldtype:"Float",precision:6,reqd:1,default:0},
			{fieldname:"waste_area",label:"Отходы",fieldtype:"Float",precision:6,reqd:1,default:0},
			{fieldname:"notes",label:"Примечание",fieldtype:"Small Text"},
		];
		for (const df of definitions) {
			this.cutting_fields[df.fieldname] = frappe.ui.form.make_control({
				parent: $("<div></div>").appendTo(controls),
				df:{...df,onchange:()=>{this.cutting_revision++;if(this.cutting_review)this.cutting_review.empty();}},render_input:true,
			});
		}
		$("<button type='button' class='btn btn-default sv-review'>Считать оставшуюся площадь отходами</button>").appendTo(this.cutting_panel).on("click", () => {
			const input = Number(this.cutting_fields.input_area.get_value());
			const used = Number(this.cutting_fields.used_area.get_value());
			const reusable = Number(this.cutting_fields.reusable_area.get_value());
			const rest = Math.round((input - used - reusable) * 1000000) / 1000000;
			if (![input,used,reusable,rest].every(Number.isFinite) || input <= 0 || used < 0 || reusable < 0 || rest < 0) return frappe.msgprint("Проверьте исходную площадь, площадь деталей и пригодного остатка.");
			this.cutting_fields.waste_area.set_value(rest);
		});
		this.cutting_button = $("<button type='button' class='btn btn-primary sv-review'>Проверить раскрой</button>").appendTo(this.cutting_panel).on("click", () => this.evaluate_cutting());
		this.cutting_review = $("<div aria-live='polite'></div>").appendTo(this.cutting_panel);
	}

	async evaluate_cutting() {
		if (this.cutting_busy) return;
		const args = {};
		for (const [key,control] of Object.entries(this.cutting_fields)) args[key] = control.get_value();
		args.skin_reference = args.skin_reference || "";
		args.notes = args.notes || "";
		const revision = this.cutting_revision;
		this.cutting_busy = true;
		this.cutting_button.prop("disabled",true);
		this.cutting_review.empty();
		try {
			const result = await frappe.xcall("erpnext.svoenrav.cutting.evaluate_cutting",args);
			if (revision !== this.cutting_revision) return;
			this.cutting_review_controls = this.render_review(this.cutting_review,result.document,{key:"cutting",label:"Раскрой без складских движений",target:"SVOENRAV Cutting Draft"},()=>revision === this.cutting_revision,args.work_order);
		} catch(error) {
			if (revision === this.cutting_revision) this.cutting_review.text("Раскрой не подтверждён. Проверьте сообщение ERPNext, единицу и баланс площадей.");
		} finally {
			this.cutting_busy = false;
			this.cutting_button.prop("disabled",false);
		}
	}

	build_order() {
		this.order_panel.append("<h2>Карточка заказа</h2>");
		if (!this.options.can_read_orders) {
			this.order_panel.append($("<p></p>").text("Нет права чтения заказов покупателей."));
			return;
		}
		this.order_field = frappe.ui.form.make_control({
			parent: this.order_panel,
			df: {fieldtype: "Link", label: "Заказ покупателя", options: "Sales Order", fieldname: "sales_order", onchange: () => this.load_order()},
			render_input: true,
		});
		$("<button type='button' class='btn btn-default sv-review'>Обновить карточку</button>").appendTo(this.order_panel).on("click", () => this.load_order());
		this.card = $("<div aria-live='polite'></div>").appendTo(this.order_panel);
	}

	async load_order() {
		if (!this.card) return;
		const request_id = ++this.request_id;
		this.history_request_id++;
		const name = this.order_field.get_value();
		this.card.empty();
		if (!name) return;
		this.card.text("Загружаем заказ…");
		try {
			const data = await frappe.xcall("erpnext.svoenrav.workshop.get_order_card", {sales_order: name});
			if (request_id !== this.request_id) return;
			this.render_order(data);
		} catch (error) {
			if (request_id === this.request_id) this.card.text("Не удалось открыть заказ. Проверьте его наличие и права доступа.");
		}
	}

	table(host, headings, rows) {
		if (!rows.length) return $("<p class='sv-help'>Нет доступных связанных документов.</p>").appendTo(host);
		const table = $("<table></table>").appendTo($("<div class='sv-table-wrap'></div>").appendTo(host));
		const head = $("<tr></tr>").appendTo($("<thead></thead>").appendTo(table));
		headings.forEach((label) => $("<th scope='col'></th>").text(label).appendTo(head));
		const body = $("<tbody></tbody>").appendTo(table);
		rows.forEach((cells) => {
			const tr = $("<tr></tr>").appendTo(body);
			cells.forEach((value) => {
				const td = $("<td></td>").appendTo(tr);
				if (value instanceof HTMLElement) td.append(value);
				else td.text(value == null ? "—" : String(value));
			});
		});
	}

	link(row) {
		const a = document.createElement("a");
		a.textContent = row.name;
		// Only local Desk URLs are accepted even though the server builds them.
		const url = new URL(row.url, window.location.href);
		if (url.origin === window.location.origin && /^\/(desk|app)\//.test(url.pathname)) a.href = url.href;
		return a;
	}

	render_order(data) {
		this.card.empty();
		const order = data.order;
		$("<h3></h3>").text(order.customer_name || order.name).appendTo(this.card);
		this.card.append(this.link({name: "Открыть полный заказ " + order.name, url: data.url}));
		const summary = $("<div class='sv-summary'></div>").appendTo(this.card);
		for (const [label, value] of [
			["Статус", __(order.status || "Draft")],
			["Срок", order.delivery_date || "—"],
			["Сумма заказа", `${order.grand_total ?? "—"} ${order.currency || ""}`],
			["Аванс по заказу", `${order.advance_paid ?? "—"} ${order.currency || ""}`],
			["Отгружено", `${order.per_delivered ?? 0}%`],
			["Выставлено счетов", `${order.per_billed ?? 0}%`],
		]) {
			const box = $("<div></div>").appendTo(summary);
			if (["Сумма заказа", "Аванс по заказу", "Выставлено счетов"].includes(label)) box.addClass("sv-finance");
			$("<span></span>").text(label).appendTo(box);
			$("<strong></strong>").text(value).appendTo(box);
		}
		this.render_order_steps(data);
		$("<button type='button' class='btn btn-default sv-advanced'>История изменения состояний</button>").appendTo(this.card).on("click", () => this.load_history(order.name));
		this.history_body = $("<div class='sv-advanced' aria-live='polite'></div>").appendTo(this.card);
		$("<h3>Состав заказа</h3>").appendTo(this.card);
		this.table(this.card, ["Изделие", "Количество", "Отгружено", "Срок"], data.items.map((row) => [row.item_name || row.item_code, `${row.qty} ${row.uom || ""}`, `${row.delivered_qty ?? 0} ${row.uom || ""}`, row.delivery_date]));
		this.related("Производство", data.production, ["Документ", "Изделие", "Готово / план", "Статус", "Материалы"], (row) => [this.link(row), row.item_name, `${row.produced_qty ?? 0} / ${row.qty}`, this.status(row), this.material_button(row.name)]);
		this.related("Материалы и выпуск", data.stock, ["Документ", "Операция", "Задание", "Состояние"], (row) => [this.link(row), __(row.purpose), row.work_order, this.status(row)]);
		this.related("Отгрузки", data.deliveries, ["Документ", "Дата", "Статус"], (row) => [this.link(row), row.posting_date, this.status(row)]);
		this.related("Счета покупателю", data.invoices, ["Документ", "Сумма", "Остаток к оплате", "Статус"], (row) => [this.link(row), `${row.grand_total} ${row.currency}`, `${row.outstanding_amount} ${row.currency}`, this.status(row)]);
		if (data.payments) {
			const finance = $("<div class='sv-finance'></div>").appendTo(this.card);
			$("<h3>Платёжные документы</h3>").appendTo(finance);
			if (data.payments.allowed) this.table(finance, ["Документ", "Дата", "Тип", "Списано / валюта", "Получено / валюта", "Состояние"], data.payments.rows.map(row => [this.link(row), row.posting_date, row.payment_type, `${row.paid_amount ?? "—"} ${row.paid_from_account_currency || ""}`, `${row.received_amount ?? "—"} ${row.paid_to_account_currency || ""}`, this.status(row)]));
			else $("<p>Нет права чтения платежей.</p>").appendTo(finance);
			if(data.payments.allowed) {
				this.table(finance, ["Платёж", "Доля заказа", "Валюта", "Распределение"], data.payments.rows.map(row => [row.name,row.order_amount,row.order_currency,{exact:"Точная доля",needs_split:"Требуется распределение",not_submitted:"Не проведён",unavailable:"Нет данных"}[row.allocation_state] || "Нет данных"]));
				for(const row of data.payments.rows) for(const allocation of row.allocation_links || []) finance.append(this.link({name:"Изменить долю заказа в " + row.name,url:allocation.url}));
				if(this.options.can_allocate_payments) for(const row of data.payments.rows) for(const reference of row.allocation_references || []) finance.append(this.link({name:"Распределить " + row.name + " · " + reference.reference,url:reference.url}));
				if(data.payments.order_totals) for(const [currency,total] of Object.entries(data.payments.order_totals)) $("<p></p>").text("Распределено на заказ: " + total + " " + currency).appendTo(finance);
				else if(data.payments.allocations_complete === false) $("<p></p>").text("Общий итог не определён: есть нераспределённые или недоступные суммы.").appendTo(finance);
			}
			$("<p class='sv-help'></p>").text(data.payments.note).appendTo(finance);
			if (data.payments.has_more) $("<p>Список неполный: проверьте штатные документы.</p>").appendTo(finance);
		}
		if (data.timeline) {
			$("<h3>Последние изменения документов</h3>").appendTo(this.card);
			this.table(this.card, ["Изменён", "Тип", "Документ", "Состояние"], data.timeline.rows.map(row => [row.at, row.doctype, this.link(row), this.status(row)]));
			$("<p class='sv-help'></p>").text(data.timeline.notice + (data.timeline.partial ? " Доступен неполный список." : "")).appendTo(this.card);
		}
		$("<p class='sv-help'></p>").text("Отображаются только доступные вам документы. Аванс относится к заказу; расчёты после выставления счетов смотрите по остаткам соответствующих счетов. Связанные документы показаны по последнему изменению, включая черновики и отмены.").appendTo(this.card);
	}

	status(row) {
		if (row.docstatus === 2) return "Отменён";
		if (row.docstatus === 0) return "Черновик";
		return row.status ? __(row.status) : "Проведён";
	}

	related(title, section, headings, build_row) {
		const host = title === "Счета покупателю" ? $("<div class='sv-finance'></div>").appendTo(this.card) : this.card;
		$("<h3></h3>").text(title).appendTo(host);
		if (!section.allowed) return $("<p class='sv-help'></p>").text("Раздел недоступен по правам чтения связанных документов.").appendTo(host);
		this.table(host, headings, section.rows.map(build_row));
		if (section.has_more) $("<p class='sv-help'></p>").text(section.note || "Показаны последние 20 документов. Остальные доступны в полном списке ERPNext.").appendTo(host);
	}

	build_queue() {
		this.queue_panel.append("<h2>Очередь производства</h2>");
		$("<p class='sv-help'></p>").text("Порядок: ручной приоритет (меньшее число раньше), затем срок и дата создания. Без ручного приоритета — после заданий с приоритетом. Паузы остаются видимыми на своём месте. Это очередь заданий, а не расчёт загрузки смен.").appendTo(this.queue_panel);
		if (!this.options.can_read_work_orders) {
			this.queue_panel.append($("<p></p>").text("Нет права чтения производственных заданий."));
			return;
		}
		$("<button type='button' class='btn btn-default sv-review'>Обновить очередь</button>").appendTo(this.queue_panel).on("click", () => this.load_queue(this.queue_start || 0));
		this.queue_settings = $("<div></div>").appendTo(this.queue_panel);
		this.queue_body = $("<div aria-live='polite'></div>").appendTo(this.queue_panel);
		this.queue_paging = $("<div class='sv-tabs'></div>").appendTo(this.queue_panel);
	}

	async load_queue(start = 0) {
		if (!this.queue_body) return;
		const request = ++this.queue_request_id;
		this.queue_body.text("Загружаем очередь…");
		this.queue_paging.empty();
		this.queue_settings.empty();
		try {
			const data = await frappe.xcall("erpnext.svoenrav.production.get_production_queue", {start});
			if (request !== this.queue_request_id) return;
			this.queue_start = data.start;
			this.queue_body.empty();
			if (data.can_configure) this.queue_settings.append(this.link({name: "Настроить приоритеты и паузы", url: data.settings_url}));
			$("<p class='sv-help'></p>").text(`Доступно заданий: ${data.total}. Показано: ${data.rows.length}.`).appendTo(this.queue_body);
			this.table(this.queue_body, ["Приоритет", "Задание", "Изделие", "Готово / план", "Срок", "Состояние", "Причина / примечание", "Материалы"], data.rows.map((row) => [
				row.priority ?? "Без ручного",
				this.link(row), row.item_name,
				`${row.produced_qty ?? 0} / ${row.qty} ${row.stock_uom || ""}`,
				(row.expected_delivery_date || "Не задан") + (row.overdue ? " · Просрочено" : ""),
				row.native_stopped ? "Задание остановлено" : row.planning_paused ? "Пауза планирования" : __(row.status),
				row.reason || "—",
				this.material_button(row.name),
			]));
			if (data.start > 0) $("<button type='button' class='btn btn-default'>Назад</button>").appendTo(this.queue_paging).on("click", () => this.load_queue(Math.max(data.start - 50, 0)));
			if (data.has_more) $("<button type='button' class='btn btn-default'>Следующие 50</button>").appendTo(this.queue_paging).on("click", () => this.load_queue(data.start + 50));
		} catch (error) {
			if (request === this.queue_request_id) this.queue_body.text("Не удалось загрузить очередь. Проверьте сообщение ERPNext, права и настройки приоритетов.");
		}
	}

	material_button(name) {
		return $("<button type='button' class='btn btn-default btn-xs'>Материалы</button>")
			.on("click", () => this.open_materials(name))[0];
	}

	open_materials(name) {
		this.show("materials");
		if (!this.material_field) return;
		if (this.material_field.get_value() === name) this.load_materials();
		else this.material_field.set_value(name);
	}

	build_materials() {
		this.material_panel.append("<h2>Материалы производственного задания</h2>");
		if (!this.options.can_read_work_orders) {
			this.material_panel.append($("<p></p>").text("Нет права чтения производственных заданий."));
			return;
		}
		this.material_field = frappe.ui.form.make_control({
			parent: this.material_panel,
			df: {fieldtype: "Link", label: "Производственное задание", options: "Work Order", fieldname: "material_work_order", get_query: () => ({filters: {docstatus: 1, status: ["not in", ["Completed", "Closed", "Cancelled"]]}}), onchange: () => this.load_materials()},
			render_input: true,
		});
		$("<button type='button' class='btn btn-default sv-review'>Обновить проверку</button>").appendTo(this.material_panel).on("click", () => this.load_materials());
		this.material_body = $("<div aria-live='polite'></div>").appendTo(this.material_panel);
		$("<button type='button' class='btn btn-default sv-review'>Проверить зафиксированный состав</button>").appendTo(this.material_panel).on("click", () => this.load_specification());
		this.spec_body = $("<div aria-live='polite'></div>").appendTo(this.material_panel);
	}

	async load_materials() {
		if (!this.material_body) return;
		const request = ++this.material_request_id;
		const name = this.material_field.get_value();
		this.spec_request_id++;
		if(this.spec_body)this.spec_body.empty();
		this.material_body.empty();
		if (!name) return;
		this.material_body.text("Проверяем материалы…");
		try {
			const data = await frappe.xcall("erpnext.svoenrav.materials.get_material_coverage", {work_order: name});
			if (request !== this.material_request_id) return;
			this.material_body.empty();
			const labels = {reserved: "Потребность к выдаче покрыта резервами задания", unreserved: "Есть свободный, но не закреплённый остаток", shortage: "Есть дефицит для выдачи", issued: "План выдачи материалов выполнен", unknown: "Недостаточно данных", review: "Требуется проверка"};
			$("<h3></h3>").text(labels[data.status] || labels.unknown).appendTo(this.material_body);
			this.material_body.append(this.link({name: "Открыть задание " + data.work_order, url: data.url}));
			$("<p class='sv-help'></p>").text("Проверено: " + data.checked_at + ". " + data.notice).appendTo(this.material_body);
			if (data.review_required) $("<p class='sv-help'></p>").text("В задании есть особые условия производства. Числа ниже справочные; проверьте полную форму задания.").appendTo(this.material_body);
			const amount = (row, key) => row[key] == null ? "—" : String(row[key]);
			this.table(this.material_body, ["Материал / ед.", "Склад", "План / выдано", "Осталось выдать", "На складе", "Все резервы", "Резерв задания", "Свободно", "Нехватка", "Проверка"], data.rows.map((row) => [
				`${row.item_name} · ${row.stock_uom}`, row.warehouse,
				`${amount(row, "required")} / ${amount(row, "transferred")}`,
				amount(row, "pending"), amount(row, "actual"), amount(row, "reserved_total"),
				amount(row, "own_reserved"), amount(row, "free"), amount(row, "shortage"),
				row.note || labels[row.status] || labels.unknown,
			]));
		} catch (error) {
			if (request === this.material_request_id) this.material_body.text("Проверка не выполнена. Проверьте сообщение ERPNext, доступ к материалам и складам. Отсутствие данных не считается нулевым остатком.");
		}
	}

	render_order_steps(data) {
		const host = $("<div></div>").appendTo(this.card);
		$("<h3>Работа по заказу</h3>").appendTo(host);
		const active = data.order.docstatus === 1 && !["Closed", "Completed", "Cancelled", "On Hold"].includes(data.order.status);
		if (!active) return $("<p>Для действий нужен действующий проведённый заказ. Проверьте полную форму.</p>").appendTo(host);
		if (!data.production.allowed) $("<p>Производство недоступно по правам; готовность не определена.</p>").appendTo(host);
		else if (!data.production.rows.length) $("<p>Связанные задания не найдены. Создайте Work Order из штатной формы заказа, проверив состав и BOM.</p>").appendTo(host);
		else {
			for (const row of data.production.rows) {
				const line = $("<div class='sv-tabs'></div>").appendTo(host);
				$("<strong></strong>").text(row.name + " · " + (row.item_name || "")).appendTo(line);
				line.append(this.material_button(row.name));
				if (row.docstatus !== 1 || ["Stopped", "Closed", "Completed", "Cancelled"].includes(row.status)) continue;
				const amounts = [row.qty,row.produced_qty,row.material_transferred_for_manufacturing];
				let next = "Проверьте материалы, нормы и полную форму задания.";
				if(amounts.every(value => value != null && Number.isFinite(Number(value)))) {
					if(Number(row.produced_qty) >= Number(row.qty)) next = "План выпуска выполнен. Проверьте готовые изделия и отгрузку.";
					else if(row.skip_transfer) next = "Задание без передачи материалов: проверьте наличие и фактический расход в полной форме.";
					else if(Number(row.material_transferred_for_manufacturing) > Number(row.produced_qty)) next = "Есть выданные материалы. Проверьте раскрой и фактический расход перед выпуском.";
					else next = "Проверьте обеспечение материалами и выдачу в производство.";
				}
				$("<p class='sv-help'></p>").text(next).appendTo(host);
				for (const key of ["transfer", "manufacture"]) {
					const spec = this.options.operations.find(op => op.key === key);
					if(spec) $("<button type='button' class='btn btn-default'></button>").text(spec.label).appendTo(line).on("click", () => this.open_operation(key, row.name));
				}
				if(this.options.can_cutting) $("<button type='button' class='btn btn-default'>Раскрой</button>").appendTo(line).on("click", async () => {
					await this.cutting_fields.work_order.set_value(row.name); this.show("cutting");
				});
			}
		}
		if (data.production.has_more) $("<p>Показаны не все задания. Общая готовность заказа не рассчитана.</p>").appendTo(host);
		const delivery = this.options.operations.find(op => op.key === "delivery");
		if(delivery && Number(data.order.per_delivered) < 100) $("<button type='button' class='btn btn-default'>Проверить отгрузку заказа</button>").appendTo(host).on("click", () => this.open_operation("delivery", data.order.name));
		$("<p class='sv-help'></p>").text("Следующий шаг: проверьте материалы задания, существующие черновики и фактическую готовность. Кнопки — переходы к проверке; они не подтверждают наличие и не проводят документы.").appendTo(host);
	}

	async load_history(name) {
		const request = ++this.history_request_id;
		const host = this.history_body;
		host.text("Загружаем записанные изменения…");
		try {
			const data = await frappe.xcall("erpnext.svoenrav.history.get_order_history", {sales_order:name});
			if(request !== this.history_request_id) return;
			host.empty();
			if(data.allowed) this.table(host,["Дата", "Документ", "Поле", "Было", "Стало"],data.rows.map(row=>[row.at,this.link(row),({status:"Статус",docstatus:"Состояние документа",qty:"План выпуска",produced_qty:"Выпущено",material_transferred_for_manufacturing:"Материалы выданы на количество",per_delivered:"Отгружено, %",per_billed:"Выставлено счетов, %",norms_hash:"Версия состава материалов",references_hash:"Версия распределения платежа",reserved_qty:"Зарезервировано",transferred_qty:"Передано",consumed_qty:"Израсходовано",amount:"Доля платежа",paid_amount:"Списано",received_amount:"Получено",bom_no:"Спецификация",production_item:"Изделие"})[row.field] || row.field,row.field.endsWith("_hash") && row.before ? String(row.before).slice(0,8) : row.before,row.field.endsWith("_hash") && row.after ? String(row.after).slice(0,8) : row.after]));
			$("<p class='sv-help'></p>").text(data.notice + (data.partial ? " История неполная." : "")).appendTo(host);
		} catch(error) { if(request === this.history_request_id) host.text("История не загружена. Проверьте сообщение ERPNext."); }
	}

	build_plan() {
		this.plan_panel.append("<h2>План материалов по очереди</h2><p class='sv-help'>Сначала собственные резервы задания, затем свободный остаток по приоритету. Паузы не получают свободный остаток. Только доступные задания, максимум 50. Расчёт не создаёт резервов.</p>");
		$("<button type='button' class='btn btn-default'>Рассчитать план</button>").appendTo(this.plan_panel).on("click", () => this.load_plan());
		if(this.options.can_reserve) this.reserve_button = $("<button type='button' class='btn btn-primary sv-review' disabled>Создать складские резервы по очереди</button>").appendTo(this.plan_panel).on("click", () => this.reserve_plan());
		this.plan_body = $("<div aria-live='polite'></div>").appendTo(this.plan_panel);
	}

	async load_plan() {
		const request = ++this.plan_request_id;
		this.plan_body.text("Рассчитываем доступную очередь…");
		if(this.reserve_button)this.reserve_button.prop("disabled",true);
		try {
			const data = await frappe.xcall("erpnext.svoenrav.planning.get_queue_plan");
			if(request !== this.plan_request_id) return;
			this.plan_body.empty();
			if(this.reserve_button)this.reserve_button.prop("disabled",!data.complete);
			$("<p></p>").text((data.complete ? "План рассчитан. " : "Неполные данные: распределение не выполнено. ") + data.checked_at).appendTo(this.plan_body);
			$("<p class='sv-help'></p>").text(data.scope).appendTo(this.plan_body);
			const labels={paused:"Пауза",unknown:"Не определено",shortage:"Дефицит",covered:"Потребность покрыта в плане"};
			for(const order of data.orders){
				$("<h3></h3>").text(order.work_order + " · " + labels[order.status]).appendTo(this.plan_body);
				this.table(this.plan_body,["Материал", "Склад", "Единица", "Осталось выдать", "Свой резерв", "Выделено в плане", "Дефицит"],order.rows.map(row=>[row.item_name||row.item_code,row.warehouse,row.stock_uom,row.pending,row.own_reserved,row.planned_free,row.shortage]));
			}
		} catch(error) { if(request === this.plan_request_id) this.plan_body.text("План не рассчитан. Проверьте права, полноту очереди и сообщение ERPNext."); }
	}

	reserve_plan() {
		if(this.reserve_busy || !this.reserve_button || this.reserve_button.prop("disabled")) return;
		frappe.confirm("Создать и провести штатные резервы материалов по актуальной очереди? Это изменит складские резервы. Перед выполнением сервер пересчитает план.", async () => {
			if(this.reserve_busy) return;
			this.reserve_busy = true; this.reserve_button.prop("disabled",true);
			this.plan_request_id++;
			try {
				const result = await frappe.xcall("erpnext.svoenrav.reservations.reserve_queue");
				await this.load_plan();
				$("<p></p>").text("Создано резервов: " + result.count + ". " + result.notice).appendTo(this.plan_body);
				for(const row of result.created) this.plan_body.append(this.link(row));
			} catch(error) { this.plan_body.text("Резервирование не выполнено. Проверьте сообщение ERPNext и обновите план. При потере связи сначала проверьте фактические резервы."); }
			finally { this.reserve_busy = false; }
		});
	}

	async load_specification(capture = false) {
		const name = this.material_field?.get_value();
		if(!name || this.spec_busy) return;
		const request = ++this.spec_request_id;
		this.spec_busy = true;
		this.spec_body.text(capture ? "Сохраняем неизменяемый снимок норм…" : "Проверяем состав…");
		try {
			const data = await frappe.xcall("erpnext.svoenrav.specifications." + (capture ? "capture_specification" : "get_specification"), {work_order:name});
			if(request !== this.spec_request_id) return;
			this.spec_body.empty();
			const labels={matches:"Нормы совпадают со снимком",changed:"Внимание: нормы задания отличаются от снимка",missing:"Состав ещё не зафиксирован",unavailable:"Снимок существует, но недоступен по правам"};
			$("<h3></h3>").text(labels[data.state] || "Нет данных состава").appendTo(this.spec_body);
			if(data.url) this.spec_body.append(this.link(data));
			if(data.payload) {
				try {
					const spec = JSON.parse(data.payload);
					$("<p></p>").text("Изделие: " + spec.production_item + " · Количество: " + spec.qty + " " + spec.stock_uom + " · Спецификация: " + spec.bom_no).appendTo(this.spec_body);
					this.table(this.spec_body,["Материал", "Норма на задание", "Единица", "Операция"],(spec.items || []).map(row=>[row.item_code,row.required_qty,row.stock_uom,row.operation]));
				} catch(error) { $("<pre></pre>").text(data.payload).appendTo(this.spec_body); }
			}
			if(data.pack) {
				try {
					const pack = JSON.parse(data.pack);
					$("<p></p>").text("Зафиксировано спецификаций: " + Object.keys(pack.boms || {}).length + ". Вложений с метаданными: " + (pack.attachments || []).length).appendTo(this.spec_body);
					this.table(this.spec_body,["Операция", "Рабочее место", "Норма времени, мин"],(pack.operations || []).map(row=>[row.operation,row.workstation,row.time_in_mins]));
				} catch(error) { $("<p>Пакет недоступен для отображения.</p>").appendTo(this.spec_body); }
			}
			$("<p class='sv-help'></p>").text(data.notice || "Фиксация сохраняет текущие нормы задания. Ранее действовавшую версию BOM она не восстанавливает.").appendTo(this.spec_body);
			if(data.state === "missing" && data.can_capture) $("<button type='button' class='btn btn-primary'>Зафиксировать текущие нормы</button>").appendTo(this.spec_body).on("click", () => this.load_specification(true));
		} catch(error) { if(request === this.spec_request_id) this.spec_body.text("Состав не проверен. Проверьте права и сообщение ERPNext."); }
		finally { this.spec_busy = false; }
	}

	build_policy() {
		this.policy_panel.append("<h2>Единый сценарий расхода материалов</h2>");
		const steps = $("<ol></ol>").appendTo(this.policy_panel);
		[
			"Заказ покупателя определяет изделие, количество и срок. Сам заказ материалы не списывает.",
			"Производственное задание использует состав и нормы BOM.",
			"Выдача в производство перемещает материалы на производственный склад.",
			"При выпуске проверьте фактический расход и готовое количество. Для этих же материалов не оформляется дополнительный Material Issue.",
			"Пригодный остаток, который ещё числится в запасе, возвращается перемещением. Уже списанный материал нельзя просто оприходовать по нулевой цене.",
		].forEach((text) => $("<li></li>").text(text).appendTo(steps));
		$("<p class='sv-help'></p>").text("Короткие формы подготавливают штатные документы ERPNext. Проверка остатков, себестоимость и проведение остаются в стандартных документах. Для отдельного потребления, технологических потерь, полуфабрикатов, Job Card и сложных производственных сценариев используйте полную форму задания. Короткий путь для них выдаст пояснение.").appendTo(this.policy_panel);
	}
}
