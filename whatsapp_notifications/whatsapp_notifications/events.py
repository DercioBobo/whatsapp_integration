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
    "WhatsApp Approval Request",
    "WhatsApp Approval Template",
    "WhatsApp Approval Option",
    "WhatsApp Auto Report",
)


def handle_after_insert(doc, method=None):
    """Handle after_insert event for all DocTypes"""
    process_event(doc, "after_insert")
    # Check for approval triggers
    check_approval_event_trigger(doc, "After Insert")


def handle_on_update(doc, method=None):
    """Handle on_update event for all DocTypes"""
    process_event(doc, "on_update")
    # Check for approval triggers
    check_approval_event_trigger(doc, "On Update")
    # Also check for workflow state changes (for non-submittable documents)
    check_workflow_state_for_approval(doc)


def handle_on_submit(doc, method=None):
    """Handle on_submit event for all DocTypes"""
    process_event(doc, "on_submit")
    # Check for approval triggers
    check_approval_event_trigger(doc, "On Submit")


def handle_on_cancel(doc, method=None):
    """Handle on_cancel event for all DocTypes"""
    process_event(doc, "on_cancel")
    # Check for approval triggers
    check_approval_event_trigger(doc, "On Cancel")


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

    # Get message_type early for debug logging
    message_type = getattr(rule, 'message_type', 'Text Only') or 'Text Only'

    # Debug: log rule processing start
    if settings.get("enable_debug_logging"):
        frappe.log_error(
            "Processing rule: {} | message_type: {} | Doc: {}".format(
                rule.name, message_type, doc.name
            ),
            "WhatsApp Rule Processing"
        )

    # Check if rule is applicable
    if not rule.is_applicable(doc, get_event_name(rule.event)):
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Rule {} not applicable for doc {}".format(rule.name, doc.name),
                "WhatsApp Rule Processing"
            )
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
                fixed_file_url=getattr(rule, 'fixed_file', None)
            )
        except Exception as e:
            frappe.log_error(
                "WhatsApp Send Error ({} to {}): {}".format(rule.name, phone_or_group, str(e)),
                "WhatsApp Send Error"
            )

    # Send to owner/default notification numbers if configured
    if rule.notify_owner and settings.get("owner_number"):
        owner_message = rule.render_message(doc, for_owner=True)

        # Support multiple numbers (one per line)
        owner_numbers = settings.get("owner_number", "").strip().split("\n")
        for owner_num in owner_numbers:
            owner_num = owner_num.strip()
            if not owner_num:
                continue
            try:
                send_notification(
                    phone=owner_num,
                    message=owner_message,
                    reference_doctype=doc.doctype,
                    reference_name=doc.name,
                    notification_rule=rule.name,
                    recipient_name="Default Notification",
                    scheduled_time=scheduled_time,
                    settings=settings,
                    message_type=message_type,
                    print_format=getattr(rule, 'print_format', None),
                    fixed_file_url=getattr(rule, 'fixed_file', None)
                )
            except Exception as e:
                frappe.log_error(
                    "WhatsApp Owner Send Error ({} to {}): {}".format(rule.name, owner_num, str(e)),
                    "WhatsApp Send Error"
                )


def is_group_id(recipient):
    """Check if the recipient is a WhatsApp group ID"""
    return recipient and isinstance(recipient, str) and "@g.us" in recipient


def send_notification(phone, message, reference_doctype, reference_name,
                      notification_rule, recipient_name, scheduled_time, settings,
                      message_type="Text Only", print_format=None, fixed_file_url=None):
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
        message_type: Type of message (Text Only, Attached File, Document PDF, Fixed File)
        print_format: Print format for PDF generation
        fixed_file_url: URL of fixed file to send (for Fixed File message type)
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

    # Normalize message_type (backward compatibility for old values)
    # Old values: "Text + Attached File", "Text + Document PDF"
    # New values: "Attached File", "Document PDF"
    if message_type in ("Text + Attached File",):
        message_type = "Attached File"
    elif message_type in ("Text + Document PDF",):
        message_type = "Document PDF"

    # Determine if this is a media message
    is_media = message_type in ("Document PDF", "Attached File", "Fixed File")

    # Debug logging
    if settings.get("enable_debug_logging"):
        frappe.log_error(
            "send_notification: message_type='{}' | is_media={} | phone={} | rule={}".format(
                message_type, is_media, phone, notification_rule
            ),
            "WhatsApp Send Debug"
        )

    if is_media:
        # Determine media source - use exact matching to avoid confusion
        use_attachment = (message_type == "Attached File")
        use_pdf = (message_type == "Document PDF")
        use_fixed_file = (message_type == "Fixed File")

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Media notification: use_attachment={} | use_pdf={} | use_fixed_file={} | print_format={}".format(
                    use_attachment, use_pdf, use_fixed_file, print_format
                ),
                "WhatsApp Media Debug"
            )

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
            use_attachment=use_attachment,
            use_pdf=use_pdf,
            use_fixed_file=use_fixed_file,
            fixed_file_url=fixed_file_url
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
                            print_format=None, use_attachment=False, use_pdf=False,
                            use_fixed_file=False, fixed_file_url=None):
    """
    Send a media notification (document PDF, attachment, or fixed file)

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
        use_attachment: Whether to send attached file from document
        use_pdf: Whether to generate and send PDF
        use_fixed_file: Whether to send a fixed file
        fixed_file_url: URL of the fixed file to send
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.api import (
        process_media_message_log, get_document_pdf, get_file_as_base64
    )

    # Debug logging
    if settings.get("enable_debug_logging"):
        frappe.log_error(
            "send_media_notification called: phone={} | use_attachment={} | use_pdf={} | use_fixed_file={} | fixed_file={}".format(
                phone, use_attachment, use_pdf, use_fixed_file, fixed_file_url
            ),
            "WhatsApp Media Function Entry"
        )

    try:
        # Determine what to send
        media_base64 = None
        mimetype = None
        filename = None
        file_size = 0
        media_type = "document"

        if use_attachment:
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
                    frappe.log_error(
                        "Could not read attachment for {} {}: {}".format(
                            reference_doctype, reference_name, file_data.get("error")
                        ),
                        "WhatsApp Attachment Error"
                    )
                    return
            else:
                frappe.log_error(
                    "No attachments found for {} {}".format(reference_doctype, reference_name),
                    "WhatsApp Attachment Error"
                )
                return

        elif use_fixed_file:
            # Send a fixed/static file (catalog, price list, etc.)
            if not fixed_file_url:
                frappe.log_error(
                    "Fixed file not configured for rule {}".format(notification_rule),
                    "WhatsApp Fixed File Error"
                )
                return

            file_data = get_file_as_base64(fixed_file_url)
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
                frappe.log_error(
                    "Could not read fixed file {}: {}".format(
                        fixed_file_url, file_data.get("error")
                    ),
                    "WhatsApp Fixed File Error"
                )
                return

        elif use_pdf:
            # Generate PDF from document
            pdf_data = get_document_pdf(reference_doctype, reference_name, print_format)
            if pdf_data.get("success"):
                media_base64 = pdf_data["base64"]
                mimetype = "application/pdf"
                filename = pdf_data["filename"]
                file_size = pdf_data.get("size", 0)
                media_type = "document"
            else:
                error_msg = pdf_data.get("error", "Unknown error")
                # Check if it's a wkhtmltopdf error
                if "wkhtmltopdf" in error_msg.lower():
                    frappe.log_error(
                        "PDF generation failed - wkhtmltopdf not installed. "
                        "Please install wkhtmltopdf on the server or use 'Attached File' option instead. "
                        "Document: {} {}".format(reference_doctype, reference_name),
                        "WhatsApp PDF Error - wkhtmltopdf Missing"
                    )
                else:
                    frappe.log_error(
                        "Could not generate PDF for {} {}: {}".format(
                            reference_doctype, reference_name, error_msg
                        ),
                        "WhatsApp PDF Error"
                    )
                return
        else:
            # No media source specified
            frappe.log_error(
                "No media source specified for {} {}".format(reference_doctype, reference_name),
                "WhatsApp Media Error"
            )
            return

        # Debug: log media preparation success
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Media prepared: filename={} | mimetype={} | size={} | media_type={}".format(
                    filename, mimetype, file_size, media_type
                ),
                "WhatsApp Media Prepared"
            )

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


def check_workflow_state_for_approval(doc):
    """
    Check if workflow state changed and trigger approval if configured

    Args:
        doc: The document that was updated
    """
    # Skip if document doesn't have workflow_state
    if not hasattr(doc, "workflow_state") or not doc.workflow_state:
        return

    # Check if workflow_state changed
    if not doc.has_value_changed("workflow_state"):
        return

    try:
        # Delegate to approval handler
        from whatsapp_notifications.whatsapp_notifications.approval import handle_workflow_state_change
        handle_workflow_state_change(doc)
    except Exception:
        # Fail silently - table might not exist during migration
        pass


def check_approval_event_trigger(doc, event):
    """
    Check if there are approval templates triggered by this event

    Args:
        doc: The document
        event: Event name (After Insert, On Update, On Submit, On Cancel)
    """
    # Skip system doctypes
    if doc.doctype in SYSTEM_DOCTYPES:
        return

    try:
        # Delegate to approval handler
        from whatsapp_notifications.whatsapp_notifications.approval import handle_document_event
        handle_document_event(doc, event)
    except Exception:
        # Fail silently - table might not exist during migration
        pass
