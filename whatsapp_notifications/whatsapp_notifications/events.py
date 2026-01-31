"""
WhatsApp Notifications - Event Handlers
Handles document events and triggers WhatsApp notifications
"""
import frappe
from frappe import _

# System DocTypes to ignore - these fire frequently and should never trigger notifications
SYSTEM_DOCTYPES = (
    # Frappe core system doctypes
    "Scheduled Job Type",
    "Scheduled Job Log", 
    "Scheduler Log",
    "Error Log",
    "Activity Log",
    "Access Log",
    "Route History",
    "View Log",
    "Energy Point Log",
    "Notification Log",
    "Email Queue",
    "Email Queue Recipient",
    "Comment",
    "Communication",
    "Version",
    "Document Follow",
    
    # Background job related
    "RQ Job",
    "RQ Worker",
    
    # Session and auth
    "User",
    "Session Default Settings",
    "Sessions",
    "Token Cache",
    
    # File and data import
    "File",
    "Data Import",
    "Data Import Log",
    "Prepared Report",
    
    # Translations
    "Translation",
    
    # WhatsApp Notifications own doctypes (prevent recursion)
    "WhatsApp Message Log",
    "Evolution API Settings",
)


def handle_after_insert(doc, method=None):
    """Handle after_insert event for all DocTypes"""
    process_event(doc, "after_insert")


def handle_on_update(doc, method=None):
    """Handle on_update event for all DocTypes"""
    process_event(doc, "on_update")


def handle_on_submit(doc, method=None):
    """Handle on_submit event for all DocTypes"""
    process_event(doc, "on_submit")


def handle_on_cancel(doc, method=None):
    """Handle on_cancel event for all DocTypes"""
    process_event(doc, "on_cancel")


def handle_on_trash(doc, method=None):
    """Handle on_trash event for all DocTypes"""
    process_event(doc, "on_trash")


def process_event(doc, event):
    """
    Process a document event and trigger any matching notification rules

    Args:
        doc: The document triggering the event
        event: Event type (after_insert, on_update, etc.)
    """
    # Skip system doctypes early (performance optimization)
    if doc.doctype in SYSTEM_DOCTYPES:
        return

    # Skip if doctype starts with __ (internal)
    if doc.doctype.startswith("__"):
        return

    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_rules_for_doctype

    try:
        # Quick check if enabled
        settings = get_settings()
        if not settings.get("enabled"):
            return

        # Get applicable rules
        rules = get_rules_for_doctype(doc.doctype, event)

        # Debug logging
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Event: {} | DocType: {} | Doc: {} | Rules found: {}".format(
                    event, doc.doctype, doc.name, len(rules)
                ),
                "WhatsApp Event Debug"
            )

        if not rules:
            return

        # Process each rule
        for rule in rules:
            try:
                # Debug: check if rule is applicable
                if settings.get("enable_debug_logging"):
                    is_applicable = rule.is_applicable(doc, event)
                    frappe.log_error(
                        "Rule: {} | Applicable: {} | Doc: {}".format(
                            rule.name, is_applicable, doc.name
                        ),
                        "WhatsApp Rule Debug"
                    )

                process_rule(doc, rule, settings)
            except Exception as e:
                frappe.log_error(
                    "WhatsApp Rule Error ({} on {}): {}".format(
                        rule.name, doc.name, str(e)
                    ),
                    "WhatsApp Rule Error"
                )

    except Exception as e:
        # Don't let notification errors break document operations
        frappe.log_error(
            "WhatsApp Event Error ({} {}): {}".format(
                event, doc.doctype, str(e)
            ),
            "WhatsApp Event Error"
        )


def process_rule(doc, rule, settings):
    """
    Process a single notification rule for a document

    Args:
        doc: The document
        rule: WhatsApp Notification Rule document
        settings: Evolution API Settings dict
    """
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number

    # Check if rule is applicable
    if not rule.is_applicable(doc, get_event_name(rule.event)):
        return

    # Get recipients
    recipients = rule.get_recipients(doc)

    if not recipients and not rule.notify_owner:
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "No recipients for rule {} on {}".format(rule.name, doc.name),
                "WhatsApp Debug"
            )
        return

    # Render message
    message = rule.render_message(doc)

    # For text-only, message is required
    message_type = getattr(rule, 'message_type', 'Text Only') or 'Text Only'
    if message_type == 'Text Only' and not message:
        frappe.log_error(
            "Empty message for rule {} on {}".format(rule.name, doc.name),
            "WhatsApp Template Error"
        )
        return

    # Calculate delay if needed
    scheduled_time = None
    if rule.delay_seconds and rule.delay_seconds > 0:
        scheduled_time = frappe.utils.add_to_date(
            frappe.utils.now_datetime(),
            seconds=rule.delay_seconds
        )

    # Send to all recipients
    for recipient in recipients:
        try:
            # Handle both new format (dict) and legacy format (string)
            if isinstance(recipient, dict):
                phone_or_group = recipient["value"]
                recipient_type = recipient["type"]
            else:
                # Legacy format (string)
                phone_or_group = recipient
                recipient_type = "phone"

            # Get recipient name if available (only for phone recipients)
            if recipient_type == "phone":
                recipient_name = get_recipient_name(doc, rule.phone_field)
            else:
                # For groups, use the group name from the rule
                recipient_name = rule.group_name or "Group"

            send_notification(
                phone=phone_or_group,
                message=message,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
                notification_rule=rule.name,
                recipient_name=recipient_name,
                scheduled_time=scheduled_time,
                settings=settings,
                message_type=message_type,
                print_format=getattr(rule, 'print_format', None),
                attach_document=getattr(rule, 'attach_document', False)
            )
        except Exception as e:
            frappe.log_error(
                "WhatsApp Send Error ({} to {}): {}".format(rule.name, phone_or_group, str(e)),
                "WhatsApp Send Error"
            )

    # Send to owner if configured
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
                settings=settings,
                message_type=message_type,
                print_format=getattr(rule, 'print_format', None),
                attach_document=getattr(rule, 'attach_document', False)
            )
        except Exception as e:
            frappe.log_error(
                "WhatsApp Owner Send Error ({}): {}".format(rule.name, str(e)),
                "WhatsApp Send Error"
            )


def is_group_id(recipient):
    """Check if the recipient is a WhatsApp group ID"""
    return recipient and isinstance(recipient, str) and "@g.us" in recipient


def send_notification(phone, message, reference_doctype, reference_name,
                      notification_rule, recipient_name, scheduled_time, settings,
                      message_type="Text Only", print_format=None, attach_document=False):
    """
    Create message log and optionally send immediately

    Args:
        phone: Recipient phone or group ID
        message: Message content
        reference_doctype: Source DocType
        reference_name: Source document
        notification_rule: Rule name
        recipient_name: Recipient display name
        scheduled_time: When to send (None = immediate)
        settings: API settings dict
        message_type: Type of message (Text Only, Document PDF, Text + Document PDF)
        print_format: Print format for PDF generation
        attach_document: Whether to attach an existing file instead of generating PDF
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    from whatsapp_notifications.whatsapp_notifications.api import process_message_log, process_media_message_log

    # Format phone number (skip for group IDs)
    if is_group_id(phone):
        formatted_phone = phone  # Use group ID as-is
    else:
        formatted_phone = format_phone_number(phone)

        if not formatted_phone:
            frappe.log_error(
                "Invalid phone number: {}".format(phone),
                "WhatsApp Phone Error"
            )
            return

    # Determine if this is a media message
    is_media = message_type in ("Document PDF", "Text + Document PDF")

    if is_media:
        # Handle media message
        send_media_notification(
            phone=phone,
            formatted_phone=formatted_phone,
            message=message,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            notification_rule=notification_rule,
            recipient_name=recipient_name,
            scheduled_time=scheduled_time,
            settings=settings,
            print_format=print_format,
            attach_document=attach_document
        )
    else:
        # Handle text-only message
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

        # Determine how to send
        if scheduled_time:
            # Scheduled for future - will be picked up by scheduler
            pass
        elif settings.get("queue_enabled"):
            # Queue for background processing
            frappe.enqueue(
                "whatsapp_notifications.whatsapp_notifications.api.process_message_log",
                log_name=log.name,
                queue="short"
            )
        else:
            # Send immediately (synchronous)
            process_message_log(log.name)


def send_media_notification(phone, formatted_phone, message, reference_doctype, reference_name,
                            notification_rule, recipient_name, scheduled_time, settings,
                            print_format=None, attach_document=False):
    """
    Send a media notification (document PDF or attachment)

    Args:
        phone: Original phone number
        formatted_phone: Formatted phone number
        message: Caption/message content
        reference_doctype: Source DocType
        reference_name: Source document
        notification_rule: Rule name
        recipient_name: Recipient display name
        scheduled_time: When to send (None = immediate)
        settings: API settings dict
        print_format: Print format for PDF generation
        attach_document: Whether to use attached file instead of generating PDF
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.api import (
        process_media_message_log, get_document_pdf, get_file_as_base64
    )

    try:
        # Determine what to send
        file_url = None
        media_base64 = None
        mimetype = None
        filename = None
        file_size = 0
        media_type = "document"

        if attach_document:
            # Try to get first attached file
            attachments = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": reference_doctype,
                    "attached_to_name": reference_name
                },
                fields=["file_url", "file_name"],
                limit=1
            )

            if attachments:
                file_url = attachments[0].file_url
                file_data = get_file_as_base64(file_url)
                if file_data.get("success"):
                    media_base64 = file_data["base64"]
                    mimetype = file_data["mimetype"]
                    filename = file_data["filename"]
                    file_size = file_data.get("size", 0)

                    # Determine media type from mimetype
                    if mimetype.startswith("image/"):
                        media_type = "image"
                    elif mimetype.startswith("video/"):
                        media_type = "video"
                    elif mimetype.startswith("audio/"):
                        media_type = "audio"
                    else:
                        media_type = "document"
                else:
                    # Fall back to PDF generation
                    attach_document = False

        if not attach_document or not media_base64:
            # Generate PDF from document
            pdf_data = get_document_pdf(reference_doctype, reference_name, print_format)
            if pdf_data.get("success"):
                media_base64 = pdf_data["base64"]
                mimetype = "application/pdf"
                filename = pdf_data["filename"]
                file_size = pdf_data.get("size", 0)
                media_type = "document"
            else:
                frappe.log_error(
                    "Could not generate PDF for {} {}: {}".format(
                        reference_doctype, reference_name, pdf_data.get("error")
                    ),
                    "WhatsApp PDF Error"
                )
                return

        # Create message log with media details
        log = create_message_log(
            phone=phone,
            message=message or "",
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            notification_rule=notification_rule,
            recipient_name=recipient_name,
            formatted_phone=formatted_phone,
            scheduled_time=scheduled_time,
            message_type="Document",
            media_type=media_type,
            file_name=filename,
            file_size=file_size,
            caption=message
        )

        # Store media data temporarily
        log.db_set("_media_base64", media_base64, update_modified=False)
        log.db_set("_media_mimetype", mimetype, update_modified=False)
        frappe.db.commit()

        # Determine how to send
        if scheduled_time:
            # Scheduled for future - will be picked up by scheduler
            pass
        elif settings.get("queue_enabled"):
            # Queue for background processing
            frappe.enqueue(
                "whatsapp_notifications.whatsapp_notifications.api.process_media_message_log",
                log_name=log.name,
                queue="short"
            )
        else:
            # Send immediately (synchronous)
            process_media_message_log(log.name)

    except Exception as e:
        frappe.log_error(
            "WhatsApp Media Notification Error ({} {}): {}".format(
                reference_doctype, reference_name, str(e)
            ),
            "WhatsApp Media Error"
        )


def get_event_name(event_label):
    """
    Convert event label to event name
    
    Args:
        event_label: Event label from rule (e.g., "After Insert")
    
    Returns:
        str: Event name (e.g., "after_insert")
    """
    event_map = {
        "After Insert": "after_insert",
        "On Update": "on_update",
        "On Submit": "on_submit",
        "On Cancel": "on_cancel",
        "On Change": "on_change",
        "On Trash": "on_trash"
    }
    return event_map.get(event_label, event_label.lower().replace(" ", "_"))


def get_recipient_name(doc, phone_field):
    """
    Try to get recipient name from document
    
    Args:
        doc: The document
        phone_field: The phone field path
    
    Returns:
        str: Recipient name or None
    """
    # Common name fields to check
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
        "employee_name",
        "nome"  # Portuguese
    ]
    
    for field in name_fields:
        if hasattr(doc, field):
            value = getattr(doc, field)
            if value:
                return str(value)
    
    return None
