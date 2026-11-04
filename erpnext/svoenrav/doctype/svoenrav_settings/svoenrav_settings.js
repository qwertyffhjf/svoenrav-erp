// License: GNU General Public License v3. See license.txt
frappe.ui.form.on("SVOENRAV Settings", {
	refresh(frm) {
		if (!frm.perm.some((row) => row.write)) return;
		const copy = (kind) => frappe.confirm(
			"Заменить строки таблицы выбранным меню? Текущее меню берётся из сохранённых настроек. Изменения применятся после сохранения формы; старый JSON сохраняется.",
			async () => {
				if (frm.__sv_copying) return;
				frm.__sv_copying = true;
				try {
					const rows = await frappe.xcall("erpnext.svoenrav.doctype.svoenrav_settings.svoenrav_settings.get_menu_editor_rows", {kind});
					frm.clear_table("menu_items");
					for (const row of rows) frm.add_child("menu_items", row);
					await frm.set_value("menu_source", "Таблица");
					frm.refresh_field("menu_items");
					frm.dirty();
				} finally {
					frm.__sv_copying = false;
				}
			}
		);
		frm.add_custom_button("Перенести сохранённое меню в таблицу", () => copy("current"));
		frm.add_custom_button("Заполнить стандартным меню", () => copy("defaults"));
	},
});

frappe.ui.form.on("SVOENRAV Menu Action", {
	async guided_operation(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const targets = {"Приёмка": "Purchase Receipt", "Выдача в производство": "Stock Entry", "Выпуск": "Stock Entry", "Отгрузка": "Delivery Note"};
		if (!targets[row.guided_operation]) return;
		await frappe.model.set_value(cdt, cdn, {
			action_doctype: targets[row.guided_operation], open_mode: "Новый документ",
			menu_section: "Быстрые действия", stock_preset: "",
		});
	},
});
