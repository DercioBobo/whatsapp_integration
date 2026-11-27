"""
WhatsApp Notifications - Webhook Handler
Receives incoming messages from Evolution API.
Approvals are answered on the approval page (see approval.py), not by replying.
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

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Message from {}: {}".format(sender_phone, message_text[:100]),
                "WhatsApp Webhook - Incoming Message"
            )

        return {"status": "ok", "message": "Received"}

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
