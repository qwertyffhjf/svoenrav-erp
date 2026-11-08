# License: GNU General Public License v3. See license.txt
"""Make Russian selectable before the native first-run wizard starts."""
import frappe


def setup():
	# Frappe ships ru in geo/languages.csv, but disabled. The native wizard
	# only offers enabled languages. Do not replace the required company setup.
	language = frappe.get_doc('Language', 'ru')
	if not language.enabled:
		language.enabled = 1
		language.save()
	# Existing installations retain their chosen system and user languages.
	if not frappe.db.get_single_value('System Settings', 'setup_complete'):
		if frappe.db.get_single_value('System Settings', 'language') in (None, '', 'en'):
			frappe.db.set_single_value('System Settings', 'language', 'ru')
		if frappe.db.get_value('User', 'Administrator', 'language') in (None, '', 'en'):
			frappe.db.set_value('User', 'Administrator', 'language', 'ru')
	frappe.clear_cache()
