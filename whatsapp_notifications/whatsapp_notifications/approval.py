"""
WhatsApp Notifications - Approval Logic
Handles sending approval requests and processing responses.

Each recipient receives a WhatsApp message with a personal, single-use link
(/approval?t=<token>). The link opens a page showing the document and one
button per response option; nothing is executed until a button is pressed
(WhatsApp link previews and phone scanners only ever GET the page).
"""
import hashlib
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime


APPROVAL_PAGE_ROUTE = "approval"


def hash_token(token):
    """Only the SHA-256 of a token is stored, so a DB read never reveals a usable link"""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def generate_token():
    return secrets.token_urlsafe(32)


def get_approval_link(token):
    return frappe.utils.get_url("/{}?t={}".format(APPROVAL_PAGE_ROUTE, token))


def get_request_by_token(token):
    """Return the WhatsApp Approval Request for a link token, or None"""
    if not token or len(token) > 128:
        return None

    name = frappe.db.get_value(
        "WhatsApp Approval Request", {"token_hash": hash_token(token)}, "name"
    )
    return frappe.get_doc("WhatsApp Approval Request", name) if name else None


def send_approval_request(doctype, docname, template_name, phone=None, enqueue=True):
    """
    Send an approval request via WhatsApp

    Args:
        doctype: Document type
        docname: Document name
        template_name: WhatsApp Approval Template name
        phone: Override phone number (optional, uses template's recipients if not provided)
        enqueue: If True, send via background job for faster response

    Returns:
        dict: Result with success status and approval request name
    """
    if enqueue:
        # Queue for background processing
        frappe.enqueue(
            "whatsapp_notifications.whatsapp_notifications.approval._send_approval_request_background",
            queue="short",
            doctype=doctype,
            docname=docname,
            template_name=template_name,
            phone=phone
        )
        return {"success": True, "message": _("Approval request queued for sending")}

    return _send_approval_request_impl(doctype, docname, template_name, phone)


def _send_approval_request_background(doctype, docname, template_name, phone=None):
    """Background job wrapper for send_approval_request"""
    try:
        result = _send_approval_request_impl(doctype, docname, template_name, phone)
        if not result.get("success"):
            frappe.log_error(
                "Background approval request failed: {}".format(result.get("error")),
                "WhatsApp Approval Background Error"
            )
    except Exception as e:
        frappe.log_error(
            "Background approval request error: {}".format(str(e)),
            "WhatsApp Approval Background Error"
        )


def _send_approval_request_impl(doctype, docname, template_name, phone=None):
    """
    Internal implementation of send_approval_request
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

        # Check condition if set
        if not template.check_condition(doc):
            return {"success": False, "error": _("Condition not met for this document")}

        # Get recipients
        if phone:
            # Override with provided phone
            recipients = [phone]
        else:
            recipients = template.get_recipients(doc)

        if not recipients:
            return {"success": False, "error": _("Could not determine recipient phone numbers")}

        # Cancel previous pending requests if not allowed
        if not template.allow_multiple_pending:
            from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_request.whatsapp_approval_request import cancel_pending_requests_for_document
            cancel_pending_requests_for_document(doctype, docname, "New approval request sent")

        # Create approval requests for all recipients
        approval_requests = []
        for recipient_phone in recipients:
            # Format phone number
            formatted_phone = format_phone_number(recipient_phone)
            if not formatted_phone:
                frappe.log_error(
                    "Invalid phone number skipped: {}".format(recipient_phone),
                    "WhatsApp Approval Warning"
                )
                continue

            # Each recipient gets their own link, so "who responded" is known
            # and one recipient's link can't act on another's request
            token = generate_token()

            # Create approval request record
            approval_request = frappe.get_doc({
                "doctype": "WhatsApp Approval Request",
                "status": "Pending",
                "approval_template": template_name,
                "reference_doctype": doctype,
                "reference_name": docname,
                "recipient_phone": recipient_phone,
                "formatted_phone": formatted_phone,
                "recipient_name": get_recipient_name_from_document(doc),
                "token_hash": hash_token(token)
            })
            approval_request.insert(ignore_permissions=True)
            approval_requests.append(approval_request)

            message = template.render_message(doc, get_approval_link(token))

            # Send WhatsApp message
            result = send_whatsapp_notification(
                phone=recipient_phone,
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

                # Add timeline comment to the original document
                from whatsapp_notifications.whatsapp_notifications.utils import add_approval_sent_comment
                add_approval_sent_comment(
                    doctype,
                    docname,
                    recipient_phone,
                    template_name,
                    approval_request.recipient_name
                )
            else:
                # Failed to send
                approval_request.mark_error(result.get("error", "Failed to send message"))

        frappe.db.commit()

        if not approval_requests:
            return {"success": False, "error": _("No valid recipients found")}

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Approval requests sent: {} for {} {} to {} recipients".format(
                    [ar.name for ar in approval_requests], doctype, docname, len(approval_requests)
                ),
                "WhatsApp Approval Debug"
            )

        return {
            "success": True,
            "approval_requests": [ar.name for ar in approval_requests],
            "recipients": len(approval_requests)
        }

    except Exception as e:
        frappe.log_error(
            "Error sending approval request for {} {}: {}".format(doctype, docname, str(e)),
            "WhatsApp Approval Error"
        )
        return {"success": False, "error": str(e)}


def process_approval_response(approval_request_name, option_number, response_text, response_from):
    """
    Process an approval response

    The caller is responsible for authenticating the responder (the approval
    page does it with the link token).

    Args:
        approval_request_name: WhatsApp Approval Request name
        option_number: Selected option number
        response_text: Free-text comment left by the responder (optional)
        response_from: Who responded (stored for audit)

    Returns:
        dict: Result with success status
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    try:
        settings = get_settings()

        approval_request = frappe.get_doc("WhatsApp Approval Request", approval_request_name)

        # Serialize responses for the same document: two approvers (or a
        # double-tap) clicking at once must not both run the action.
        frappe.db.sql(
            "select name from `tab{}` where name=%s for update".format(approval_request.reference_doctype),
            approval_request.reference_name
        )
        approval_request.reload()

        # Check if already processed (duplicate response)
        if approval_request.status != "Pending":
            return {
                "success": False,
                "already_processed": True,
                "error": _("This approval request has already been processed (status: {0})").format(
                    approval_request.status
                )
            }

        # Check expiry
        if approval_request.is_expired():
            approval_request.mark_expired()
            return {"success": False, "error": _("This approval request has expired")}

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
        action_result = execute_action_as(doc, option, template.action_user)

        if action_result.get("success"):
            # Determine status based on option label
            new_status = determine_status_from_option(option.option_label)
            approval_request.mark_processed(action_result.get("description"), new_status)

            # Add timeline comment to the original document
            from whatsapp_notifications.whatsapp_notifications.utils import add_approval_response_comment
            add_approval_response_comment(
                approval_request.reference_doctype,
                approval_request.reference_name,
                response_from,
                option.option_label,
                new_status
            )

            # If first_response_wins, cancel other pending requests for same document
            if template.first_response_wins:
                cancel_other_pending_requests(
                    approval_request.reference_doctype,
                    approval_request.reference_name,
                    approval_request.name,
                    "Approval already processed by another recipient"
                )

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


def cancel_other_pending_requests(doctype, docname, except_request_name, reason):
    """
    Cancel all other pending requests for a document except the one specified

    Args:
        doctype: Document type
        docname: Document name
        except_request_name: Request name to exclude
        reason: Cancellation reason
    """
    requests = frappe.get_all(
        "WhatsApp Approval Request",
        filters={
            "status": "Pending",
            "reference_doctype": doctype,
            "reference_name": docname,
            "name": ["!=", except_request_name]
        }
    )

    for req in requests:
        frappe.db.set_value(
            "WhatsApp Approval Request",
            req.name,
            {
                "status": "Cancelled",
                "error_message": reason
            }
        )


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


def execute_action_as(doc, option, user=None):
    """
    Run execute_action as a real user. The approval page is opened without
    login (session user Guest), and Guest can't pass workflow role checks, so
    the action runs as the template's Action User (default: Administrator).
    """
    original_user = frappe.session.user
    # set_user() also resets session.data and form_dict; keep the caller's
    # so a logged-in visitor's session (csrf token etc.) isn't wiped
    saved_session_data = frappe.local.session.data
    saved_form_dict = frappe.local.form_dict
    try:
        frappe.set_user(user or "Administrator")
        return execute_action(doc, option)
    finally:
        frappe.set_user(original_user)
        frappe.local.session.data = saved_session_data
        frappe.local.form_dict = saved_form_dict


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
    try:
        from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
        from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_template.whatsapp_approval_template import get_template_for_workflow_state

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

        # Check condition
        if not template.check_condition(doc):
            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "Approval condition not met for {} {}".format(doc.doctype, doc.name),
                    "WhatsApp Approval Condition"
                )
            return

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Workflow state change detected: {} {} -> {}".format(
                    doc.doctype, doc.name, doc.workflow_state
                ),
                "WhatsApp Approval Trigger"
            )

        # Send approval request (enqueued for faster response)
        send_approval_request(
            doctype=doc.doctype,
            docname=doc.name,
            template_name=template.name,
            enqueue=True
        )

    except Exception:
        # Fail silently - table might not exist during migration
        pass


def handle_document_event(doc, event):
    """
    Handle document events to trigger automatic approvals

    Args:
        doc: Document
        event: Event name (After Insert, On Update, On Submit, On Cancel)
    """
    try:
        from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
        from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_template.whatsapp_approval_template import get_templates_for_event

        settings = get_settings()
        if not settings.get("enabled"):
            return

        # Get matching templates for this event
        templates = get_templates_for_event(doc.doctype, event)

        if not templates:
            return

        for template in templates:
            # Check condition
            if not template.check_condition(doc):
                if settings.get("enable_debug_logging"):
                    frappe.log_error(
                        "Approval condition not met for template {} on {} {}".format(
                            template.name, doc.doctype, doc.name
                        ),
                        "WhatsApp Approval Condition"
                    )
                continue

            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "Event trigger: {} on {} {} - template {}".format(
                        event, doc.doctype, doc.name, template.name
                    ),
                    "WhatsApp Approval Trigger"
                )

            # Send approval request (enqueued for faster response)
            send_approval_request(
                doctype=doc.doctype,
                docname=doc.name,
                template_name=template.name,
                enqueue=True
            )

    except Exception as e:
        # Log error if debug enabled, otherwise fail silently
        try:
            from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
            settings = get_settings()
            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "handle_document_event error for {} {} ({}): {}".format(
                        doc.doctype, doc.name, event, str(e)
                    ),
                    "WhatsApp Approval Event Error"
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Approval page (/approval?t=<token>) - no login required
# ---------------------------------------------------------------------------

def get_approval_page_state(token):
    """
    Build everything the approval page shows for a token. Read-only: opening
    the link never changes anything.

    Returns:
        dict with "state" in: invalid, pending, expired, done, resolved_by_other,
        cancelled, error - plus display data
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    approval_request = get_request_by_token(token)
    if not approval_request:
        return {"state": "invalid"}

    if not get_settings().get("enabled"):
        return {"state": "invalid"}

    template = frappe.get_doc("WhatsApp Approval Template", approval_request.approval_template)

    out = {
        "reference_doctype": approval_request.reference_doctype,
        "reference_name": approval_request.reference_name,
        "status": approval_request.status,
        "responded_at": approval_request.responded_at,
        "expires_at": approval_request.expires_at,
        "options": [],
        "summary": "",
    }

    try:
        doc = frappe.get_doc(approval_request.reference_doctype, approval_request.reference_name)
    except frappe.DoesNotExistError:
        out["state"] = "invalid"
        return out

    if approval_request.status == "Pending" and approval_request.is_expired():
        out["state"] = "expired"
        return out

    if approval_request.status == "Pending":
        out["state"] = "pending"
        out["summary"] = template.render_summary(doc)
        out["options"] = [
            {"number": o.option_number, "label": o.option_label,
             "is_reject": determine_status_from_option(o.option_label) == "Rejected"}
            for o in sorted(template.response_options, key=lambda x: x.option_number)
        ]
        return out

    if approval_request.status in ("Approved", "Rejected"):
        out["state"] = "done"
        option = template.get_option_by_number(approval_request.response_option)
        out["chosen_label"] = option.option_label if option else approval_request.status
        return out

    if approval_request.status == "Expired":
        out["state"] = "expired"
        return out

    if approval_request.status == "Cancelled":
        resolved = _get_resolving_request(approval_request)
        if resolved:
            out["state"] = "resolved_by_other"
            out["resolved_status"] = resolved.status
            out["resolved_at"] = resolved.responded_at
            if template.already_resolved_template:
                try:
                    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_template_context
                    out["resolved_message"] = frappe.render_template(
                        template.already_resolved_template, get_template_context(doc)
                    )
                except Exception:
                    pass
        else:
            out["state"] = "cancelled"
        return out

    out["state"] = "error"
    return out


def _get_resolving_request(approval_request):
    """The request for the same document that was answered (first_response_wins)"""
    rows = frappe.get_all(
        "WhatsApp Approval Request",
        filters={
            "reference_doctype": approval_request.reference_doctype,
            "reference_name": approval_request.reference_name,
            "status": ["in", ["Approved", "Rejected"]],
            "name": ["!=", approval_request.name],
            "responded_at": [">=", approval_request.sent_at],
        },
        fields=["name"],
        order_by="responded_at asc",
        limit=1,
    )
    return frappe.get_doc("WhatsApp Approval Request", rows[0].name) if rows else None


@frappe.whitelist(allow_guest=True)
def submit_approval_response(token, option_number, comment=None):
    """
    Called by the approval page when a button is pressed. The token is the
    credential: it is long, random, per-recipient and works only while the
    request is Pending.
    """
    # POST only: link previewers and scanners issue GETs and must never act
    # (checked by hand because whitelist(methods=...) doesn't exist on v13)
    if frappe.request and frappe.request.method != "POST":
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    approval_request = get_request_by_token(token)
    if not approval_request:
        frappe.local.response.http_status_code = 404
        return {"success": False, "error": _("This approval link is not valid.")}

    try:
        option_number = int(option_number)
    except (TypeError, ValueError):
        return {"success": False, "error": _("Invalid option.")}

    comment = (comment or "").strip()[:500] or None

    request = getattr(frappe.local, "request", None)
    ip = getattr(frappe.local, "request_ip", None) or ""
    user_agent = (request.headers.get("User-Agent", "") if request else "")[:250]
    result = process_approval_response(
        approval_request_name=approval_request.name,
        option_number=option_number,
        response_text=comment,
        response_from=approval_request.recipient_phone,
    )

    if not result.get("already_processed"):
        frappe.db.set_value(
            "WhatsApp Approval Request", approval_request.name,
            {"response_ip": ip, "response_user_agent": user_agent},
            update_modified=False,
        )

    frappe.db.commit()

    if result.get("success"):
        return {"success": True, "status": result.get("status")}

    return {
        "success": False,
        "already_processed": bool(result.get("already_processed")),
        "error": result.get("error") or _("Could not process the response."),
    }
