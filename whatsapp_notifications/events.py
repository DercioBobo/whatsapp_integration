"""
WhatsApp Notifications - Event Handlers
Handles document events and triggers WhatsApp notifications
"""
import frappe
from frappe import _


def handle_after_insert(doc, method=None):
    process_event(doc, "after_insert")


def handle_on_update(doc, method=None):
    process_event(doc, "on_update")


def handle_on_submit(doc, method=None):
    process_event(doc, "on_submit")


def handle_on_cancel(doc, method=None):
    process_event(doc, "on_cancel")


def handle_on_trash(doc, method=None):
    process_event(doc, "on_trash")


SYSTEM_DOCTYPES = (
    "Scheduler Log",
    "Scheduled Job Type",
    "Error Log",
    "RQ Job",
    "RQ Worker",
    "Version",
)


def process_event(doc, event):
    # Evitar loops / ruído do sistema
    if doc.doctype in SYSTEM_DOCTYPES:
        return

    # Import paths MUST be valid Python (no "..")
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_rules_for_doctype

    try:
        settings = get_settings()
        if not settings.get("enabled"):
            return

        rules = get_rules_for_doctype(doc.doctype, event)
        if not rules:
            return

        for rule in rules:
            try:
                process_rule(doc, rule, settings)
            except Exception as e:
                frappe.log_error(
                    "WhatsApp Rule Error ({} on {}): {}".format(rule.name, doc.name, str(e)),
                    "WhatsApp Rule Error"
                )

    except Exception as e:
        frappe.log_error(
            "WhatsApp Event Error ({} {}): {}".format(event, doc.doctype, str(e)),
            "WhatsApp Event Error"
        )


def process_rule(doc, rule, settings):
    # Keep imports light
    # from whatsapp_notifications.api import send_whatsapp_notification  # not used directly here
    from whatsapp_notifications.utils import format_phone_number

    if not rule.is_applicable(doc, get_event_name(rule.event)):
        return

    recipients = rule.get_recipients(doc)

    if not recipients and not rule.notify_owner:
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "No recipients for rule {} on {}".format(rule.name, doc.name),
                "WhatsApp Debug"
            )
        return

    message = rule.render_message(doc)
    if not message:
        frappe.log_error(
            "Empty message for rule {} on {}".format(rule.name, doc.name),
            "WhatsApp Template Error"
        )
        return

    scheduled_time = None
    if rule.delay_seconds and rule.delay_seconds > 0:
        scheduled_time = frappe.utils.add_to_date(
            frappe.utils.now_datetime(),
            seconds=rule.delay_seconds
        )

    for phone in recipients:
        try:
            recipient_name = get_recipient_name(doc, rule.phone_field)
            send_notification(
                phone=phone,
                message=message,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                notification_rule=rule.name,
                recipient_name=recipient_name,
                scheduled_time=scheduled_time,
                settings=settings
            )
        except Exception as e:
            frappe.log_error(
                "WhatsApp Send Error ({} to {}): {}".format(rule.name, phone, str(e)),
                "WhatsApp Send Error"
            )

    if rule.notify_owner and settings.get("owner_number"):
        try:
            owner_message = rule.render_message(doc, for_owner=True)
            send_notification(
                phone=settings.get("owner_number"),
                message=owner_message,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                notification_rule=rule.name,
                recipient_name="Business Owner",
                scheduled_time=scheduled_time,
                settings=settings
            )
        except Exception as e:
            frappe.log_error(
                "WhatsApp Owner Send Error ({}): {}".format(rule.name, str(e)),
                "WhatsApp Send Error"
            )


def send_notification(phone, message, reference_doctype, reference_name,
                      notification_rule, recipient_name, scheduled_time, settings):
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.utils import format_phone_number
    from whatsapp_notifications.api import process_message_log

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        frappe.log_error("Invalid phone number: {}".format(phone), "WhatsApp Phone Error")
        return

    log = create_message_log(
        phone=phone,
        message=message,
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        notification_rule=notification_rule,
        recipient_name=recipient_name,
        formatted_phone=formatted_phone,
        scheduled_time=scheduled_time
    )

    # If delayed, do nothing here (your scheduler/process_pending should pick it up)
    if scheduled_time:
        return

    # No delay: queue or send immediately
    if settings.get("queue_enabled"):
        # Use callable to avoid get_attr import issues in workers
        frappe.enqueue(
            process_message_log,
            log_name=log.name,
            queue="short"
        )
    else:
        process_message_log(log.name)


def get_event_name(event_label):
    event_map = {
        "After Insert": "after_insert",
        "On Update": "on_update",
        "On Submit": "on_submit",
        "On Cancel": "on_cancel",
        "On Change": "on_change",
        "On Trash": "on_trash"
    }
    return event_map.get(event_label, (event_label or "").lower().replace(" ", "_"))


def get_recipient_name(doc, phone_field):
    name_fields = [
        "customer_name",
        "contact_name",
        "full_name",
        "name1",
        "first_name",
        "lead_name",
        "party_name",
        "customer",
        "supplier_name",
        "employee_name"
    ]

    for field in name_fields:
        if hasattr(doc, field):
            value = getattr(doc, field)
            if value:
                return str(value)

    return None
