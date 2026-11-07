# License: GNU General Public License v3. See license.txt
"""Names and unit arithmetic; no database or stock posting."""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlsplit

MAX_BATCH = 200
MAX_NUMBER = 999999999


def whole(value, label='Количество', minimum=1, maximum=MAX_NUMBER):
	if value is None or isinstance(value, bool):
		raise ValueError(label + ': требуется целое число.')
	try:
		number = Decimal(str(value))
	except (InvalidOperation, ValueError):
		raise ValueError(label + ': требуется целое число.') from None
	if not number.is_finite() or number != number.to_integral_value() or not minimum <= number <= maximum:
		raise ValueError(label + f': допустимо целое число от {minimum} до {maximum}.')
	return int(number)


def model_code(value):
	if not isinstance(value, str) or not re.fullmatch(r'[\w][\w .-]{0,79}', value.strip()):
		raise ValueError('Артикул модели: до 80 букв, цифр, пробелов, точек, дефисов или подчёркиваний.')
	return value.strip()


def image_path(value):
	if not isinstance(value, str) or len(value) > 1000:
		raise ValueError('Выберите загруженный файл фотографии.')
	url = urlsplit(value)
	if url.scheme or url.netloc or url.query or url.fragment or not url.path.startswith(('/files/', '/private/files/')) or '..' in unquote(url.path).split('/') or any(ord(c)<32 or c=='\\' for c in unquote(value)):
		raise ValueError('Фотография должна быть файлом этой ERP, без внешней ссылки.')
	return value


def number_block(start, count, digits):
	start = whole(start, 'Начальный номер')
	count = whole(count, 'Размер выпуска', maximum=MAX_BATCH)
	digits = whole(digits, 'Разрядность', maximum=12)
	if start + count - 1 > MAX_NUMBER:
		raise ValueError('Диапазон номеров исчерпан.')
	return [(value, str(value).zfill(digits)) for value in range(start, start + count)]


def unit_key(entry, detail, ordinal):
	return hashlib.sha256(f'{entry}\0{detail}\0{ordinal}'.encode()).hexdigest()
