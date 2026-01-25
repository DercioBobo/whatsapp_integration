"""
Desktop/Module Configuration for WhatsApp Notifications
"""
from frappe import _


def get_data():
    return [
        {
            "module_name": "WhatsApp Notifications",
            "color": "#25D366",  # WhatsApp green
            "icon": "octicon octicon-comment-discussion",
            "type": "module",
            "label": _("WhatsApp Notifications"),
            "description": _("Send WhatsApp notifications via Evolution API")
        }
    ]
