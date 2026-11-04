# License: GNU General Public License v3. See license.txt
"""Area balance only. No material valuation, stock conversion or posting."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

AREA_FIELDS = ("input_area", "used_area", "reusable_area", "waste_area")
AREA_UNITS = ("дм²", "м²", "см²")


def cutting_balance(values):
	if values.get("area_unit") not in AREA_UNITS:
		raise ValueError("Выберите единую единицу площади: дм², м² или см².")
	areas = {}
	for field in AREA_FIELDS:
		value = values.get(field)
		if value is None or isinstance(value, bool):
			raise ValueError("Заполните все четыре площади, включая нулевые остатки и отходы.")
		try:
			area = Decimal(str(value))
		except (InvalidOperation, ValueError):
			raise ValueError("Площади должны быть числами.") from None
		if not area.is_finite() or area < 0 or area > Decimal("1000000000"):
			raise ValueError("Площадь должна быть конечным неотрицательным числом до 1 000 000 000.")
		if area.normalize().as_tuple().exponent < -6:
			raise ValueError("Для площади допустимо не более шести знаков после запятой.")
		areas[field] = area
	if areas["input_area"] <= 0:
		raise ValueError("Исходная площадь должна быть больше нуля.")
	total = areas["used_area"] + areas["reusable_area"] + areas["waste_area"]
	if total != areas["input_area"]:
		raise ValueError("Баланс не сходится: детали + пригодный остаток + отходы должны равняться исходной площади.")
	return {
		**{key: float(value) for key, value in areas.items()},
		"area_unit": values["area_unit"],
		"consumed_area": float(areas["used_area"] + areas["waste_area"]),
		"yield_percent": float((areas["used_area"] / areas["input_area"] * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
		"balanced": True,
	}
