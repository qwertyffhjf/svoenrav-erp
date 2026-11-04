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
		this.ready = false;
		this.root = $("<div class='sv-workshop'></div>").appendTo(page.main);
		this.root.append(`<style>
		.sv-workshop{padding:20px;max-width:1200px;margin:auto}
		.sv-workshop h2{font-size:21px;margin:8px 0 16px}.sv-workshop h3{font-size:17px;margin:24px 0 12px}
		.sv-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
		.sv-tabs button{min-height:44px}.sv-panel{padding:20px;border:1px solid var(--border-color,#dce4df);border-radius:10px;margin-bottom:18px}
		.sv-controls{display:grid;grid-template-columns:1fr 1fr;gap:18px}.sv-quantity{max-width:260px}
		.sv-help{line-height:1.6;color:var(--text-muted,#647168);font-size:13px;white-space:pre-line}
		.sv-review{min-height:44px;margin-top:12px}.sv-summary{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}
		.sv-summary>div{padding:12px 16px;border:1px solid var(--border-color,#dce4df);border-radius:8px}
		.sv-summary strong{display:block;margin-top:4px}.sv-table-wrap{overflow:auto}
		.sv-workshop table{width:100%;font-size:13px}.sv-workshop td,.sv-workshop th{padding:10px;border-bottom:1px solid var(--border-color,#dce4df);vertical-align:top}
		.sv-workshop a{overflow-wrap:anywhere}.sv-feedback:empty{display:none}.sv-feedback{margin:12px 0}
		@media(max-width:600px){.sv-workshop{padding:12px}.sv-panel{padding:14px}.sv-controls{grid-template-columns:1fr;gap:0}.sv-summary>div{flex:1 1 42%}.sv-workshop td,.sv-workshop th{padding:8px}}
		</style>`);
		this.tabs = $("<nav class='sv-tabs' aria-label='Разделы мастерской'></nav>").appendTo(this.root);
		this.operation_tab = $("<button class='btn btn-default' type='button'>Операции</button>").appendTo(this.tabs).on("click", () => this.show("operations"));
		this.order_tab = $("<button class='btn btn-default' type='button'>Карточка заказа</button>").appendTo(this.tabs).on("click", () => this.show("order"));
		this.queue_tab = $("<button class='btn btn-default' type='button'>Очередь производства</button>").appendTo(this.tabs).on("click", () => this.show("queue"));
		this.material_tab = $("<button class='btn btn-default' type='button'>Материалы задания</button>").appendTo(this.tabs).on("click", () => this.show("materials"));
		this.policy_tab = $("<button class='btn btn-default' type='button'>Как учитываются материалы</button>").appendTo(this.tabs).on("click", () => this.show("policy"));
		this.feedback = $("<div class='sv-feedback text-muted' role='status'></div>").appendTo(this.root);
		this.operations_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.order_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.queue_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
		this.material_panel = $("<section class='sv-panel'></section>").appendTo(this.root);
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
			this.ready = true;
			this.feedback.empty();
			this.apply_route();
		} catch (error) {
			this.feedback.text("Не удалось загрузить доступные операции. Обновите страницу или проверьте права доступа.");
		}
	}

	show(view) {
		this.operations_panel.toggle(view === "operations");
		this.order_panel.toggle(view === "order");
		this.queue_panel.toggle(view === "queue");
		this.material_panel.toggle(view === "materials");
		this.policy_panel.toggle(view === "policy");
		for (const [key, button] of [["operations", this.operation_tab], ["order", this.order_tab], ["queue", this.queue_tab], ["materials", this.material_tab], ["policy", this.policy_tab]]) {
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
		if (route.view === "materials") return this.show("materials");
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
			df: {fieldtype: "Float", label: "Количество готовых изделий", fieldname: "quantity", description: "В единицах изделия из производственного задания; для передачи — на какое количество изделий выдаём материалы."},
			render_input: true,
		});
		this.operation_help = $("<p class='sv-help'></p>").appendTo(this.operations_panel);
		this.prepare_button = $("<button type='button' class='btn btn-primary sv-review'>Подготовить документ</button>")
			.appendTo(this.operations_panel).on("click", () => this.prepare());
		this.operation_field.set_value(this.options.operations[0].key);
		this.change_operation();
	}

	change_operation() {
		if (!this.quantity_field) return;
		const spec = this.options.operations.find((row) => row.key === this.operation_field.get_value());
		if (!spec) return;
		this.source_host.empty();
		this.quantity_field.set_value(null);
		const is_production = spec.source === "Work Order";
		const labels = {"Purchase Order": "Заказ поставщику", "Work Order": "Производственное задание", "Sales Order": "Заказ покупателя"};
		this.source_field = frappe.ui.form.make_control({
			parent: this.source_host,
			df: {fieldtype: "Link", label: labels[spec.source], options: spec.source, fieldname: "source", reqd: 1, get_query: () => ({filters: {docstatus: 1, status: ["not in", ["Stopped", "Closed", "Completed", "Cancelled", "On Hold"]]}})},
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
		try {
			const doc = await frappe.xcall("erpnext.svoenrav.workshop.prepare_operation", args);
			const docs = frappe.model.sync(doc);
			await frappe.set_route("Form", docs[0].doctype, docs[0].name);
		} catch (error) {
			this.feedback.text("Документ не подготовлен. Проверьте сообщение ERPNext и исходные данные.");
		} finally {
			this.preparing = false;
			this.prepare_button.prop("disabled", false);
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
		const url = new URL(row.url, window.location.origin);
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
			$("<span></span>").text(label).appendTo(box);
			$("<strong></strong>").text(value).appendTo(box);
		}
		$("<h3>Состав заказа</h3>").appendTo(this.card);
		this.table(this.card, ["Изделие", "Количество", "Отгружено", "Срок"], data.items.map((row) => [row.item_name || row.item_code, `${row.qty} ${row.uom || ""}`, `${row.delivered_qty ?? 0} ${row.uom || ""}`, row.delivery_date]));
		this.related("Производство", data.production, ["Документ", "Изделие", "Готово / план", "Статус", "Материалы"], (row) => [this.link(row), row.item_name, `${row.produced_qty ?? 0} / ${row.qty}`, this.status(row), this.material_button(row.name)]);
		this.related("Материалы и выпуск", data.stock, ["Документ", "Операция", "Задание", "Состояние"], (row) => [this.link(row), __(row.purpose), row.work_order, this.status(row)]);
		this.related("Отгрузки", data.deliveries, ["Документ", "Дата", "Статус"], (row) => [this.link(row), row.posting_date, this.status(row)]);
		this.related("Счета покупателю", data.invoices, ["Документ", "Сумма", "Остаток к оплате", "Статус"], (row) => [this.link(row), `${row.grand_total} ${row.currency}`, `${row.outstanding_amount} ${row.currency}`, this.status(row)]);
		$("<p class='sv-help'></p>").text("Отображаются только доступные вам документы. Аванс относится к заказу; расчёты после выставления счетов смотрите по остаткам соответствующих счетов. Связанные документы показаны по последнему изменению, включая черновики и отмены.").appendTo(this.card);
	}

	status(row) {
		if (row.docstatus === 2) return "Отменён";
		if (row.docstatus === 0) return "Черновик";
		return row.status ? __(row.status) : "Проведён";
	}

	related(title, section, headings, build_row) {
		$("<h3></h3>").text(title).appendTo(this.card);
		if (!section.allowed) return $("<p class='sv-help'></p>").text("Раздел недоступен по правам чтения связанных документов.").appendTo(this.card);
		this.table(this.card, headings, section.rows.map(build_row));
		if (section.has_more) $("<p class='sv-help'></p>").text(section.note || "Показаны последние 20 документов. Остальные доступны в полном списке ERPNext.").appendTo(this.card);
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
		return $("<button type='button' class='btn btn-default btn-xs'>Проверить</button>")
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
	}

	async load_materials() {
		if (!this.material_body) return;
		const request = ++this.material_request_id;
		const name = this.material_field.get_value();
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
