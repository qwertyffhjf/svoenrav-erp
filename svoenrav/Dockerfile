ARG ERP_BASE_IMAGE=frappe/erpnext:v16.53.0
FROM ${ERP_BASE_IMAGE}

USER frappe
# Keep the base image's matching framework, dependencies and compiled ERPNext assets.
# The added Python module and server-rendered page require no frontend asset build.
COPY --chown=frappe:frappe erpnext/ /home/frappe/frappe-bench/apps/erpnext/erpnext/
COPY --chown=frappe:frappe license.txt /home/frappe/frappe-bench/apps/erpnext/license.txt
COPY --chown=frappe:frappe README_SVOENRAV.md /home/frappe/frappe-bench/apps/erpnext/README_SVOENRAV.md
