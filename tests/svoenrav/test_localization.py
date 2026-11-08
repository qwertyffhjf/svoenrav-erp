import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


class LocalizationTests(unittest.TestCase):
	def run_setup(self, *, enabled=0, complete=0, system='en', user='en', save_error=None):
		frappe=ModuleType('frappe')
		language=SimpleNamespace(enabled=enabled, save=Mock(side_effect=save_error))
		frappe.get_doc=Mock(return_value=language)
		frappe.db=Mock()
		frappe.db.get_single_value.side_effect=lambda dt,field:complete if field=='setup_complete' else system
		frappe.db.get_value.return_value=user
		frappe.clear_cache=Mock()
		path=Path(__file__).resolve().parents[2]/'erpnext/svoenrav/localization.py'
		spec=importlib.util.spec_from_file_location('localization_test_target',path)
		module=importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules,{'frappe':frappe}):
			spec.loader.exec_module(module)
			module.setup()
		return frappe,language

	def test_first_install_enables_ru_and_sets_initial_language(self):
		f,language=self.run_setup()
		self.assertEqual(language.enabled,1);language.save.assert_called_once()
		f.db.set_single_value.assert_called_once_with('System Settings','language','ru')
		f.db.set_value.assert_called_once_with('User','Administrator','language','ru')
		f.clear_cache.assert_called_once();f.db.commit.assert_not_called()

	def test_completed_install_retains_languages_but_offers_russian(self):
		f,language=self.run_setup(complete=1)
		language.save.assert_called_once()
		f.db.set_single_value.assert_not_called();f.db.set_value.assert_not_called()

	def test_repeated_migration_does_not_resave_enabled_language(self):
		f,language=self.run_setup(enabled=1,system='ru',user='ru')
		language.save.assert_not_called()
		f.db.set_single_value.assert_not_called();f.db.set_value.assert_not_called()

	def test_explicit_nonenglish_choices_before_setup_are_preserved(self):
		f,language=self.run_setup(system='de',user='fr')
		f.db.set_single_value.assert_not_called();f.db.set_value.assert_not_called()

	def test_enable_failure_is_not_hidden(self):
		with self.assertRaises(PermissionError):
			self.run_setup(save_error=PermissionError('Cannot enable language'))
