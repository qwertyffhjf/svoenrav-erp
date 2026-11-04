# License: GNU General Public License v3. See license.txt
"""Ordering is explicit priority, due date, creation and name; never workload fill."""


def normalise_queue(rows):
	if not isinstance(rows, (list, tuple)) or len(rows) > 1000:
		raise ValueError("В настройках очереди допускается не более 1000 заданий.")
	result = {}
	for row in rows:
		if not isinstance(row, dict):
			raise ValueError("Некорректная строка приоритета.")
		name = row.get("work_order")
		if not isinstance(name, str) or not name.strip() or len(name) > 140:
			raise ValueError("Выберите производственное задание.")
		if name in result:
			raise ValueError("Задание повторяется в настройках очереди: " + name)
		raw = row.get("priority")
		if raw in (None, "", 0, "0") and not isinstance(raw, bool):
			priority = None
		else:
			if isinstance(raw, bool) or not str(raw).isdigit() or not 1 <= int(raw) <= 999999:
				raise ValueError("Приоритет — целое число от 1 до 999999; пустое поле означает без ручного приоритета.")
			priority = int(raw)
		paused = row.get("paused", 0)
		if paused not in (0, 1, "0", "1"):
			raise ValueError("Пауза задаётся флажком.")
		paused = paused in (1, "1")
		reason = row.get("reason") or ""
		if not isinstance(reason, str) or len(reason) > 500:
			raise ValueError("Причина — текст до 500 символов.")
		if paused and not reason.strip():
			raise ValueError("Для паузы укажите причину.")
		result[name] = {"priority": priority, "paused": paused, "reason": reason.strip()}
	return result


def sort_queue(orders, planning, today):
	rows = []
	for order in orders:
		row = dict(order)
		plan = planning.get(row["name"], {})
		row.update({"priority": plan.get("priority"), "planning_paused": bool(plan.get("paused")), "reason": plan.get("reason", "")})
		row["native_stopped"] = row.get("status") == "Stopped"
		date = str(row.get("expected_delivery_date") or "")[:10]
		row["overdue"] = bool(date and date < today)
		rows.append(row)
	return sorted(rows, key=lambda row: (
		row["priority"] is None, row["priority"] or 0,
		not bool(row.get("expected_delivery_date")), str(row.get("expected_delivery_date") or ""),
		str(row.get("creation") or ""), row["name"],
	))
