"""
WhatsApp Notifications - Webhook Handler
Receives incoming messages from Evolution API and processes approval responses
"""
import frappe
from frappe import _
import json
import re


@frappe.whitelist(allow_guest=True)
def receive_message():
    """
    Webhook endpoint for Evolution API incoming messages.
    URL: /api/method/whatsapp_notifications.whatsapp_notifications.webhook.receive_message

    Evolution API sends POST requests with message data when messages are received.

    Expected payload structure (Evolution API v2):
    {
        "event": "messages.upsert",
        "instance": "instance_name",
        "data": {
            "key": {
                "remoteJid": "258841234567@s.whatsapp.net",
                "fromMe": false,
                "id": "message_id"
            },
            "message": {
                "conversation": "1"  // or "extendedTextMessage": {"text": "1"}
            },
            "messageTimestamp": 1234567890,
            "pushName": "Contact Name"
        }
    }
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    try:
        settings = get_settings()

        # Get request data
        if frappe.request.data:
            try:
                data = json.loads(frappe.request.data)
            except json.JSONDecodeError:
                data = frappe.request.form or {}
        else:
            data = frappe.request.form or {}

        # Debug logging
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Webhook received: {}".format(json.dumps(data, indent=2, default=str)[:2000]),
                "WhatsApp Webhook Debug"
            )

        # Check if WhatsApp is enabled
        if not settings.get("enabled"):
            return {"status": "ok", "message": "WhatsApp notifications disabled"}

        # Parse the webhook payload
        parsed = parse_webhook_payload(data)

        if not parsed:
            # Not a message we care about (could be status update, etc.)
            return {"status": "ok", "message": "Ignored"}

        sender_phone = parsed.get("phone")
        message_text = parsed.get("text")
        push_name = parsed.get("push_name")

        if not sender_phone or not message_text:
            return {"status": "ok", "message": "Missing phone or message"}

        # Check if this is a response to a pending approval
        result = process_potential_approval_response(sender_phone, message_text, settings)

        if result.get("processed"):
            return {
                "status": "ok",
                "message": "Approval response processed",
                "result": result
            }

        # Not an approval response - could be logged or handled differently
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Message from {} not matched to approval: {}".format(sender_phone, message_text[:100]),
                "WhatsApp Webhook - No Match"
            )

        return {"status": "ok", "message": "No matching approval request"}

    except Exception as e:
        frappe.log_error(
            "Webhook error: {}".format(str(e)),
            "WhatsApp Webhook Error"
        )
        # Return 200 OK to prevent Evolution API from retrying
        return {"status": "error", "message": str(e)}


def parse_webhook_payload(data):
    """
    Parse the Evolution API webhook payload to extract message details

    Args:
        data: Webhook payload dict

    Returns:
        dict: {phone, text, push_name, message_id} or None
    """
    if not data:
        return None

    # Handle different Evolution API event types
    event = data.get("event", "")

    # We only care about incoming messages
    if event not in ("messages.upsert", "message", "messages"):
        # Could be a status update, presence, etc.
        return None

    # Get message data
    message_data = data.get("data", data)

    # Handle array of messages
    if isinstance(message_data, list):
        if not message_data:
            return None
        message_data = message_data[0]

    # Get key info
    key = message_data.get("key", {})

    # Skip outgoing messages (fromMe = true)
    if key.get("fromMe", False):
        return None

    # Extract phone number from remoteJid
    remote_jid = key.get("remoteJid", "")
    phone = extract_phone_from_jid(remote_jid)

    if not phone:
        return None

    # Extract message text
    message = message_data.get("message", {})
    text = extract_message_text(message)

    if not text:
        return None

    return {
        "phone": phone,
        "text": text.strip(),
        "push_name": message_data.get("pushName", ""),
        "message_id": key.get("id", "")
    }


def extract_phone_from_jid(jid):
    """
    Extract phone number from WhatsApp JID

    Args:
        jid: WhatsApp JID (e.g., "258841234567@s.whatsapp.net")

    Returns:
        str: Phone number or None
    """
    if not jid:
        return None

    # Handle individual chats
    if "@s.whatsapp.net" in jid:
        return jid.split("@")[0]

    # Handle group chats (we don't process these for approvals)
    if "@g.us" in jid:
        return None

    # Try to extract any numeric part
    match = re.match(r"(\d+)", jid)
    if match:
        return match.group(1)

    return None


def extract_message_text(message):
    """
    Extract text content from Evolution API message object

    Args:
        message: Message object from Evolution API

    Returns:
        str: Message text or None
    """
    if not message:
        return None

    # Direct conversation text
    if "conversation" in message:
        return message["conversation"]

    # Extended text message
    if "extendedTextMessage" in message:
        return message["extendedTextMessage"].get("text", "")

    # Button response
    if "buttonsResponseMessage" in message:
        return message["buttonsResponseMessage"].get("selectedButtonId", "")

    # List response
    if "listResponseMessage" in message:
        return message["listResponseMessage"].get("singleSelectReply", {}).get("selectedRowId", "")

    # Template button reply
    if "templateButtonReplyMessage" in message:
        return message["templateButtonReplyMessage"].get("selectedId", "")

    return None


def process_potential_approval_response(sender_phone, message_text, settings):
    """
    Check if message is a response to a pending approval and process it

    Args:
        sender_phone: Phone number that sent the message
        message_text: Message content
        settings: Evolution API settings

    Returns:
        dict: Result with processed flag
    """
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    from whatsapp_notifications.whatsapp_notifications.approval import process_approval_response

    # Format the sender phone for matching
    formatted_phone = format_phone_number(sender_phone)

    if not formatted_phone:
        # Try using the phone as-is
        formatted_phone = sender_phone

    # Find pending approval request for this phone
    approval_request = find_pending_approval_for_phone(formatted_phone, sender_phone)

    if not approval_request:
        return {"processed": False, "reason": "No pending approval for this phone"}

    # Parse the response to get option number
    option_number = parse_response_option(message_text)

    if option_number is None:
        # Invalid response - could send a help message
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Invalid response '{}' for approval {}".format(
                    message_text, approval_request.name
                ),
                "WhatsApp Approval Invalid Response"
            )

        # Send help message
        send_invalid_response_message(approval_request, message_text, settings)

        return {"processed": False, "reason": "Invalid option number"}

    # Validate option number exists in template
    template = frappe.get_doc("WhatsApp Approval Template", approval_request.approval_template)
    option = template.get_option_by_number(option_number)

    if not option:
        # Option number not valid for this template
        send_invalid_response_message(approval_request, message_text, settings)
        return {"processed": False, "reason": "Option {} not valid for this approval".format(option_number)}

    # Process the approval
    result = process_approval_response(
        approval_request_name=approval_request.name,
        option_number=option_number,
        response_text=message_text,
        response_from=sender_phone
    )

    frappe.db.commit()

    return {
        "processed": True,
        "approval_request": approval_request.name,
        "option": option_number,
        "result": result
    }


def find_pending_approval_for_phone(formatted_phone, original_phone):
    """
    Find a pending approval request for a phone number

    Tries multiple matching strategies to handle phone format variations

    Args:
        formatted_phone: Formatted phone number
        original_phone: Original phone number from webhook

    Returns:
        WhatsApp Approval Request or None
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_approval_request.whatsapp_approval_request import get_pending_request_by_phone

    # Try formatted phone first
    request = get_pending_request_by_phone(formatted_phone)
    if request:
        return request

    # Try original phone
    if original_phone != formatted_phone:
        request = get_pending_request_by_phone(original_phone)
        if request:
            return request

    # Try fuzzy matching (last 9 digits)
    clean_phone = ''.join(filter(str.isdigit, str(original_phone)))
    if len(clean_phone) >= 9:
        suffix = clean_phone[-9:]

        # Search for requests where formatted_phone ends with this suffix
        requests = frappe.get_all(
            "WhatsApp Approval Request",
            filters={
                "status": "Pending",
                "formatted_phone": ["like", "%{}".format(suffix)]
            },
            order_by="creation desc",
            limit=1
        )

        if requests:
            return frappe.get_doc("WhatsApp Approval Request", requests[0].name)

    return None


def parse_response_option(message_text):
    """
    Parse the message text to extract an option number

    Args:
        message_text: Raw message text

    Returns:
        int: Option number or None if not found
    """
    if not message_text:
        return None

    text = message_text.strip()

    # Try to parse as integer directly
    try:
        return int(text)
    except ValueError:
        pass

    # Try to find a number at the start of the message
    match = re.match(r"^(\d+)", text)
    if match:
        return int(match.group(1))

    # Try to find a standalone number anywhere
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))

    return None


def send_invalid_response_message(approval_request, received_text, settings):
    """
    Send a message explaining the valid options when invalid response received

    Args:
        approval_request: WhatsApp Approval Request
        received_text: The invalid text received
        settings: Evolution API settings
    """
    from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification

    try:
        template = frappe.get_doc("WhatsApp Approval Template", approval_request.approval_template)

        # Build help message
        message = _("Sorry, I didn't understand your response: '{0}'").format(received_text[:50])
        message += "\n\n"
        message += _("Please respond with one of these options:") + "\n"

        for option in sorted(template.response_options, key=lambda x: x.option_number):
            message += "{} - {}\n".format(option.option_number, option.option_label)

        message += "\n" + _("Reply with just the number.")

        send_whatsapp_notification(
            phone=approval_request.recipient_phone,
            message=message,
            reference_doctype="WhatsApp Approval Request",
            reference_name=approval_request.name,
            notification_rule=None,
            recipient_name=approval_request.recipient_name
        )

    except Exception as e:
        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Error sending invalid response message: {}".format(str(e)),
                "WhatsApp Webhook Error"
            )


@frappe.whitelist(allow_guest=True)
def webhook_status():
    """
    Simple endpoint to verify webhook is accessible
    URL: /api/method/whatsapp_notifications.whatsapp_notifications.webhook.webhook_status
    """
    return {
        "status": "ok",
        "app": "WhatsApp Notifications",
        "webhook": "active"
    }
