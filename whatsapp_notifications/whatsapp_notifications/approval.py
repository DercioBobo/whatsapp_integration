"""
WhatsApp Notifications - Approval Logic
Handles sending approval requests and processing responses
"""
import frappe
from frappe import _
from frappe.utils import now_datetime


def send_approval_request(doctype, docname, template_name, phone=None):
    """
    Send an approval request via WhatsApp

    Args:
        doctype: Document type
        docname: Document name
        template_name: WhatsApp Approval Template name
        phone: Override phone number (optional, uses template's phone_field if not provided)

    Returns:
        dict: Result with success status and approval request name
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification

    try:
        # Get settings
        settings = get_settings()
        if not settings.get("enabled"):
            return {"success": False, "error": _("WhatsApp notifications are disabled")}

        # Get template
        template = frappe.get_doc("WhatsApp Approval Template", template_name)
        if not template.enabled:
            return {"success": False, "error": _("Approval template is disabled")}

        # Get document
        doc = frappe.get_doc(doctype, docname)

        # Get phone number
        if not phone:
            phone = get_phone_from_document(doc, template.phone_field)

        if not phone:
            return {"success": False, "error": _("Could not determine recipient phone number")}

        # Format phone number
        formatted_phone = format_phone_number(phone)
        if not formatted_phone:
            return {"success": False, "error": _("Invalid phone number: {0}").format(phone)}

        # Cancel previous pending requests if not allowed
        if not template.allow_multiple_pending:
            from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_request.whatsapp_approval_request import cancel_pending_requests_for_document
            cancel_pending_requests_for_document(doctype, docname, "New approval request sent")

        # Render message
        message = template.render_message(doc)

        # Create approval request record
        approval_request = frappe.get_doc({
            "doctype": "WhatsApp Approval Request",
            "status": "Pending",
            "approval_template": template_name,
            "reference_doctype": doctype,
            "reference_name": docname,
            "recipient_phone": phone,
            "formatted_phone": formatted_phone,
            "recipient_name": get_recipient_name_from_document(doc)
        })
        approval_request.insert(ignore_permissions=True)

        # Send WhatsApp message
        result = send_whatsapp_notification(
            phone=phone,
            message=message,
            reference_doctype="WhatsApp Approval Request",
            reference_name=approval_request.name,
            notification_rule=None,
            recipient_name=approval_request.recipient_name
        )

        if result.get("success") or result.get("queued"):
            # Update approval request with message log reference
            if result.get("log"):
                approval_request.db_set("message_log", result.get("log"))

            frappe.db.commit()

            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "Approval request sent: {} for {} {}".format(
                        approval_request.name, doctype, docname
                    ),
                    "WhatsApp Approval Debug"
                )

            return {
                "success": True,
                "approval_request": approval_request.name,
                "message_log": result.get("log")
            }
        else:
            # Failed to send
            approval_request.mark_error(result.get("error", "Failed to send message"))
            return {"success": False, "error": result.get("error")}

    except Exception as e:
        frappe.log_error(
            "Error sending approval request for {} {}: {}".format(doctype, docname, str(e)),
            "WhatsApp Approval Error"
        )
        return {"success": False, "error": str(e)}


def process_approval_response(approval_request_name, option_number, response_text, response_from):
    """
    Process an approval response

    Args:
        approval_request_name: WhatsApp Approval Request name
        option_number: Selected option number
        response_text: Raw response text
        response_from: Phone number that responded

    Returns:
        dict: Result with success status
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    try:
        settings = get_settings()

        approval_request = frappe.get_doc("WhatsApp Approval Request", approval_request_name)

        # Validate status
        if approval_request.status != "Pending":
            return {
                "success": False,
                "error": _("This approval request is no longer pending (status: {0})").format(
                    approval_request.status
                )
            }

        # Check expiry
        if approval_request.is_expired():
            approval_request.mark_expired()
            return {"success": False, "error": _("This approval request has expired")}

        # Verify phone number matches (security check)
        if not verify_phone_match(approval_request.formatted_phone, response_from):
            frappe.log_error(
                "Phone mismatch for approval {}: expected {}, got {}".format(
                    approval_request_name, approval_request.formatted_phone, response_from
                ),
                "WhatsApp Approval Security"
            )
            return {
                "success": False,
                "error": _("Response must come from the original recipient's phone number")
            }

        # Get template and option
        template = frappe.get_doc("WhatsApp Approval Template", approval_request.approval_template)
        option = template.get_option_by_number(option_number)

        if not option:
            return {
                "success": False,
                "error": _("Invalid option number: {0}").format(option_number)
            }

        # Record the response
        approval_request.record_response(option_number, response_text, response_from)

        # Get the referenced document
        doc = frappe.get_doc(
            approval_request.reference_doctype,
            approval_request.reference_name
        )

        # Execute the action
        action_result = execute_action(doc, option)

        if action_result.get("success"):
            # Determine status based on option label
            new_status = determine_status_from_option(option.option_label)
            approval_request.mark_processed(action_result.get("description"), new_status)

            # Send confirmation if enabled
            if template.send_confirmation:
                send_confirmation_message(
                    template, doc, approval_request, option.option_label, action_result
                )

            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "Approval processed: {} - Option {} ({})".format(
                        approval_request_name, option_number, option.option_label
                    ),
                    "WhatsApp Approval Debug"
                )

            return {
                "success": True,
                "action": action_result.get("description"),
                "status": new_status
            }
        else:
            approval_request.mark_error(action_result.get("error"))
            return {"success": False, "error": action_result.get("error")}

    except Exception as e:
        frappe.log_error(
            "Error processing approval response for {}: {}".format(
                approval_request_name, str(e)
            ),
            "WhatsApp Approval Error"
        )
        return {"success": False, "error": str(e)}


def execute_action(doc, option):
    """
    Execute the action defined in an approval option

    Args:
        doc: The document to act on
        option: WhatsApp Approval Option

    Returns:
        dict: Result with success status and description
    """
    try:
        if option.action_type == "Workflow Action":
            return execute_workflow_action(doc, option.workflow_action)
        elif option.action_type == "Update Field":
            return execute_field_update(doc, option.field_to_update, option.field_value)
        elif option.action_type == "Run Method":
            return execute_custom_method(doc, option.method_path)
        else:
            return {"success": False, "error": _("Unknown action type: {0}").format(option.action_type)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_workflow_action(doc, action_name):
    """
    Execute a Frappe workflow action

    Args:
        doc: Document to apply workflow to
        action_name: Workflow action name

    Returns:
        dict: Result with success status
    """
    try:
        from frappe.model.workflow import apply_workflow

        # Apply the workflow action
        apply_workflow(doc, action_name)

        return {
            "success": True,
            "description": _("Workflow action '{0}' applied").format(action_name)
        }
    except Exception as e:
        error_msg = str(e)
        # Handle common workflow errors
        if "is not allowed" in error_msg.lower():
            return {
                "success": False,
                "error": _("Workflow action '{0}' is not allowed in current state").format(action_name)
            }
        return {"success": False, "error": error_msg}


def execute_field_update(doc, field_name, field_value):
    """
    Update a field on the document

    Args:
        doc: Document to update
        field_name: Field name to update
        field_value: New value for the field

    Returns:
        dict: Result with success status
    """
    try:
        if not hasattr(doc, field_name):
            return {
                "success": False,
                "error": _("Field '{0}' not found on {1}").format(field_name, doc.doctype)
            }

        # Set the field value
        doc.set(field_name, field_value)
        doc.save(ignore_permissions=True)

        return {
            "success": True,
            "description": _("Field '{0}' updated to '{1}'").format(field_name, field_value)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_custom_method(doc, method_path):
    """
    Execute a custom Python method

    Args:
        doc: Document to pass to the method
        method_path: Full dotted path to the method

    Returns:
        dict: Result with success status
    """
    try:
        # Import and call the method
        method = frappe.get_attr(method_path)
        result = method(doc)

        return {
            "success": True,
            "description": _("Method '{0}' executed").format(method_path),
            "result": result
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def expire_old_requests():
    """
    Scheduled task to expire old approval requests
    Should be run hourly via scheduler
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    settings = get_settings()

    # Find pending requests that have expired
    expired_requests = frappe.get_all(
        "WhatsApp Approval Request",
        filters={
            "status": "Pending",
            "expires_at": ["<", now_datetime()]
        }
    )

    count = 0
    for request in expired_requests:
        try:
            frappe.db.set_value(
                "WhatsApp Approval Request",
                request.name,
                "status",
                "Expired"
            )
            count += 1
        except Exception as e:
            frappe.log_error(
                "Error expiring approval request {}: {}".format(request.name, str(e)),
                "WhatsApp Approval Expiry Error"
            )

    if count > 0:
        frappe.db.commit()

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Expired {} approval requests".format(count),
                "WhatsApp Approval Expiry"
            )


def send_confirmation_message(template, doc, approval_request, option_label, action_result):
    """
    Send a confirmation message after processing an approval

    Args:
        template: WhatsApp Approval Template
        doc: The document that was acted on
        approval_request: WhatsApp Approval Request
        option_label: The selected option label
        action_result: Result of the action
    """
    from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification

    try:
        message = template.render_confirmation(doc, option_label, action_result)

        if message:
            send_whatsapp_notification(
                phone=approval_request.recipient_phone,
                message=message,
                reference_doctype=approval_request.reference_doctype,
                reference_name=approval_request.reference_name,
                notification_rule=None,
                recipient_name=approval_request.recipient_name
            )
    except Exception as e:
        frappe.log_error(
            "Error sending confirmation for {}: {}".format(approval_request.name, str(e)),
            "WhatsApp Approval Confirmation Error"
        )


def get_phone_from_document(doc, phone_field):
    """
    Get phone number from document using field path

    Args:
        doc: Document
        phone_field: Field path (can use dot notation for linked docs)

    Returns:
        str: Phone number or None
    """
    if not phone_field:
        return None

    try:
        # Handle dot notation (e.g., "customer.mobile_no")
        if "." in phone_field:
            parts = phone_field.split(".")
            value = doc
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                elif isinstance(value, str):
                    # It's a link field, get the linked document
                    linked_doctype = frappe.get_meta(doc.doctype).get_field(parts[0]).options
                    value = frappe.db.get_value(linked_doctype, value, part)
                else:
                    return None
            return value
        else:
            return getattr(doc, phone_field, None)
    except Exception:
        return None


def get_recipient_name_from_document(doc):
    """
    Try to get a recipient name from the document

    Args:
        doc: Document

    Returns:
        str: Recipient name or None
    """
    name_fields = [
        "full_name",
        "customer_name",
        "contact_name",
        "lead_name",
        "employee_name",
        "supplier_name",
        "name1",
        "first_name"
    ]

    for field in name_fields:
        if hasattr(doc, field):
            value = getattr(doc, field)
            if value:
                return str(value)

    return None


def verify_phone_match(expected_phone, actual_phone):
    """
    Verify that the response phone matches the expected phone

    Args:
        expected_phone: Expected formatted phone number
        actual_phone: Actual phone number from response

    Returns:
        bool: True if phones match
    """
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number

    if not expected_phone or not actual_phone:
        return False

    # Format the actual phone for comparison
    formatted_actual = format_phone_number(actual_phone)

    if not formatted_actual:
        # Try direct comparison if formatting fails
        # Clean both numbers for comparison
        clean_expected = ''.join(filter(str.isdigit, str(expected_phone)))
        clean_actual = ''.join(filter(str.isdigit, str(actual_phone)))

        # Check if one ends with the other (handle country code differences)
        return clean_expected.endswith(clean_actual[-9:]) or clean_actual.endswith(clean_expected[-9:])

    return expected_phone == formatted_actual


def determine_status_from_option(option_label):
    """
    Determine the approval request status based on option label

    Args:
        option_label: The option label text

    Returns:
        str: Status (Approved/Rejected)
    """
    label_lower = option_label.lower()

    reject_keywords = ["reject", "deny", "decline", "refuse", "no", "cancel"]
    for keyword in reject_keywords:
        if keyword in label_lower:
            return "Rejected"

    return "Approved"


def handle_workflow_state_change(doc, method=None):
    """
    Handle workflow state changes to trigger automatic approvals
    Called from doc_events hook

    Args:
        doc: Document that changed
        method: Event method name
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_template.whatsapp_approval_template import get_template_for_workflow_state

    try:
        settings = get_settings()
        if not settings.get("enabled"):
            return

        # Check if document has workflow_state
        if not hasattr(doc, "workflow_state") or not doc.workflow_state:
            return

        # Look for matching approval template
        template = get_template_for_workflow_state(doc.doctype, doc.workflow_state)

        if not template:
            return

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Workflow state change detected: {} {} -> {}".format(
                    doc.doctype, doc.name, doc.workflow_state
                ),
                "WhatsApp Approval Trigger"
            )

        # Send approval request
        result = send_approval_request(
            doctype=doc.doctype,
            docname=doc.name,
            template_name=template.name
        )

        if not result.get("success"):
            frappe.log_error(
                "Failed to send automatic approval for {} {}: {}".format(
                    doc.doctype, doc.name, result.get("error")
                ),
                "WhatsApp Approval Auto-Trigger Error"
            )

    except Exception as e:
        frappe.log_error(
            "Error in workflow state change handler for {} {}: {}".format(
                doc.doctype, doc.name, str(e)
            ),
            "WhatsApp Approval Handler Error"
        )
