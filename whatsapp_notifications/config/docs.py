"""
Module documentation configuration
"""
from frappe import _


def get_help_messages():
    """
    Returns help messages for the module
    """
    return [
        {
            "message": _("Configure Evolution API Settings to connect to your WhatsApp instance."),
            "link": "Evolution API Settings"
        },
        {
            "message": _("Create Notification Rules to automate WhatsApp messages based on document events."),
            "link": "WhatsApp Notification Rule"
        },
        {
            "message": _("View Message Logs to track all sent messages and troubleshoot issues."),
            "link": "WhatsApp Message Log"
        }
    ]


def get_data():
    """
    Returns module configuration for docs
    """
    return {
        "fieldname": "whatsapp_notifications",
        "label": _("WhatsApp Notifications"),
        "color": "#25D366",
        "icon": "octicon octicon-comment-discussion",
        "type": "module",
        "description": _("WhatsApp notification service using Evolution API")
    }
