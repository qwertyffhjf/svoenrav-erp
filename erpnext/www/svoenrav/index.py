# Copyright (c) 2026, SVOENRAV
# License: GNU General Public License v3. See license.txt

from erpnext.svoenrav.portal import get_page_context

no_cache = 1


def get_context(context):
	context.update(get_page_context())
	context.title = context.brand_name
	context.no_cache = 1
	context.no_breadcrumbs = 1
	return context
