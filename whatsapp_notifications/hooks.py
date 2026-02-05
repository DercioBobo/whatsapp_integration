"""
WhatsApp Notifications - Frappe Hooks Configuration
Defines app metadata, fixtures, scheduled tasks, and document events
"""

from . import __version__ as app_version

app_name = "whatsapp_notifications"
app_title = "WhatsApp Notifications"
app_publisher = "Entretech"
app_description = "WhatsApp Notifications for ERPNext using Evolution API"
app_email = "bobo@entretech.co.mz"
app_license = "MIT"

# Required Frappe version
required_apps = ["frappe"]

# App includes
# ------------------

# Include js, css files in header of desk.html
# app_include_css = "/assets/whatsapp_notifications/css/whatsapp_notifications.css"
app_include_js = "/assets/whatsapp_notifications/js/whatsapp_notifications.js"

# Include js, css files in header of web template
# web_include_css = "/assets/whatsapp_notifications/css/whatsapp_notifications.css"
# web_include_js = "/assets/whatsapp_notifications/js/whatsapp_notifications.js"

# Include custom scss in every website theme (without signing in)
# website_theme_scss = "whatsapp_notifications/public/scss/website"

# Include js in page
# page_js = {"page" : "public/js/file.js"}

# Include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------
# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# Automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "whatsapp_notifications.whatsapp_notifications.install.before_install"
after_install = "whatsapp_notifications.whatsapp_notifications.install.after_install"
after_migrate = "whatsapp_notifications.whatsapp_notifications.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "whatsapp_notifications.uninstall.before_uninstall"
# after_uninstall = "whatsapp_notifications.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "whatsapp_notifications.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# This is the CORE functionality - we dynamically attach to all configured DocTypes
# The actual event handlers are set up in the install.after_migrate hook
# based on WhatsApp Notification Rules

doc_events = {
    "*": {
        "after_insert": "whatsapp_notifications.whatsapp_notifications.events.handle_after_insert",
        "on_update": "whatsapp_notifications.whatsapp_notifications.events.handle_on_update",
        "on_submit": "whatsapp_notifications.whatsapp_notifications.events.handle_on_submit",
        "on_cancel": "whatsapp_notifications.whatsapp_notifications.events.handle_on_cancel",
        "on_trash": "whatsapp_notifications.whatsapp_notifications.events.handle_on_trash",
        "on_update_after_submit": "whatsapp_notifications.whatsapp_notifications.approval.handle_workflow_state_change",
    }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    # Run every minute to process pending messages
    "cron": {
        "* * * * *": [
            "whatsapp_notifications.whatsapp_notifications.tasks.process_pending_messages"
        ],
        # Retry failed messages every 5 minutes
        "*/5 * * * *": [
            "whatsapp_notifications.whatsapp_notifications.tasks.retry_failed_messages"
        ],
        # Check auto reports every 15 minutes
        "*/15 * * * *": [
            "whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_auto_report.whatsapp_auto_report.process_auto_reports"
        ],
        # Cleanup old logs daily at 2 AM
        "0 2 * * *": [
            "whatsapp_notifications.whatsapp_notifications.tasks.cleanup_old_logs"
        ]
    },
    # Alternative for older Frappe versions
    "all": [
        "whatsapp_notifications.whatsapp_notifications.tasks.process_pending_messages"
    ],
    "hourly": [
        "whatsapp_notifications.whatsapp_notifications.tasks.retry_failed_messages",
        "whatsapp_notifications.whatsapp_notifications.approval.expire_old_requests",
        "whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_auto_report.whatsapp_auto_report.process_auto_reports"
    ],
    "daily": [
        "whatsapp_notifications.whatsapp_notifications.tasks.cleanup_old_logs"
    ]
}

# Testing
# -------

# before_tests = "whatsapp_notifications.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "whatsapp_notifications.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "whatsapp_notifications.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Request Events
# ----------------
# before_request = ["whatsapp_notifications.utils.before_request"]
# after_request = ["whatsapp_notifications.utils.after_request"]

# Job Events
# ----------
# before_job = ["whatsapp_notifications.utils.before_job"]
# after_job = ["whatsapp_notifications.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"whatsapp_notifications.auth.validate"
# ]

# Fixtures - Export/Import
# ------------------------
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "WhatsApp Notifications"]]
    },
    {
        "doctype": "Property Setter",
        "filters": [["module", "=", "WhatsApp Notifications"]]
    }
]

# Jinja Environment
# -----------------
# Add custom Jinja filters/functions for templates
jinja = {
    "methods": [
        "whatsapp_notifications.whatsapp_notifications.utils.jinja_methods"
    ]
}
