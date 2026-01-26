"""
WhatsApp Notifications - Main API Module
Provides the core functionality for sending WhatsApp messages
Compatible with ERPNext v13, v14, and v15
"""
import frappe
from frappe import _


def make_http_request(url, method="POST", headers=None, data=None):
    """
    Make HTTP request compatible with v13, v14, and v15
    Forces JSON UTF-8 when sending dict payloads.
    """
    headers = headers or {}

    # If data is a dict/list, we want JSON
    is_json = isinstance(data, (dict, list))

    # Method 1: frappe.integrations.utils (v14+)
    try:
        from frappe.integrations.utils import make_post_request, make_get_request

        if method.upper() == "POST":
            if is_json:
                # Some versions support `json=`
                try:
                    return make_post_request(url, headers=headers, json=data)
                except TypeError:
                    # fallback: encode manually as UTF-8 JSON string
                    import json
                    headers["Content-Type"] = "application/json; charset=utf-8"
                    return make_post_request(url, headers=headers, data=json.dumps(data, ensure_ascii=False).encode("utf-8"))
            else:
                return make_post_request(url, headers=headers, data=data)
        else:
            return make_get_request(url, headers=headers)

    except ImportError:
        pass
    except Exception as e:
        frappe.log_error("integrations.utils failed: " + str(e), "WhatsApp HTTP Debug")

    # Method 2: frappe.make_post_request (v13)
    try:
        if method.upper() == "POST":
            if is_json:
                import json
                headers["Content-Type"] = "application/json; charset=utf-8"
                return frappe.make_post_request(
                    url,
                    headers=headers,
                    data=json.dumps(data, ensure_ascii=False).encode("utf-8")
                )
            else:
                return frappe.make_post_request(url, headers=headers, data=data)
        else:
            return frappe.make_get_request(url, headers=headers)

    except AttributeError:
        pass
    except Exception as e:
        frappe.log_error("frappe.make_post_request failed: " + str(e), "WhatsApp HTTP Debug")

    # Method 3: requests library (fallback)
    import requests
    if method.upper() == "POST":
        if is_json:
            headers["Content-Type"] = "application/json; charset=utf-8"
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            response = requests.post(url, headers=headers, data=data, timeout=30)
    else:
        response = requests.get(url, headers=headers, timeout=30)

    response.raise_for_status()
    return response.json()



@frappe.whitelist(allow_guest=False)
def send_whatsapp(phone, message, doctype=None, docname=None, queue=True):
    """
    Send a WhatsApp message via Evolution API
    
    This is the main entry point for sending WhatsApp messages.
    Can be called from client-side JavaScript or server-side Python.
    
    Args:
        phone: Recipient phone number
        message: Message content
        doctype: Optional reference DocType
        docname: Optional reference document name
        queue: If True, queue for background processing (default)
    
    Returns:
        dict: Result with success status
    
    Example:
        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp',
            args: {
                phone: '841234567',
                message: 'Hello from ERPNext!'
            }
        });
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    
    # Validate inputs
    if not phone or not message:
        return {"success": False, "error": _("Phone and message are required")}

    # Get settings
    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": _("WhatsApp notifications are disabled")}

    if not settings.get("api_url") or not settings.get("api_key") or not settings.get("instance_name"):
        return {"success": False, "error": _("Evolution API not configured")}

    # Format phone number (skip for group IDs)
    if is_group_id(phone):
        formatted_phone = phone  # Use group ID as-is
    else:
        formatted_phone = format_phone_number(phone)

        if not formatted_phone:
            return {"success": False, "error": _("Invalid phone number")}
    
    # Create message log
    log = create_message_log(
        phone=phone,
        message=message,
        reference_doctype=doctype,
        reference_name=docname,
        formatted_phone=formatted_phone
    )
    
    # Send immediately or queue based on settings
    if queue and settings.get("queue_enabled"):
        # Message will be processed by scheduled task
        return {"success": True, "message": _("Message queued"), "log": log.name}
    else:
        # Send immediately
        result = process_message_log(log.name)
        return result


def send_whatsapp_notification(phone, message, reference_doctype=None, reference_name=None,
                               notification_rule=None, recipient_name=None):
    """
    Internal function to send WhatsApp notification
    Called by event handlers and scheduled tasks
    
    Args:
        phone: Recipient phone number
        message: Message content
        reference_doctype: Source DocType
        reference_name: Source document name
        notification_rule: Triggering rule name
        recipient_name: Recipient display name
    
    Returns:
        dict: Result with success status
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    
    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": "WhatsApp notifications disabled"}

    # Format phone number (skip for group IDs)
    if is_group_id(phone):
        formatted_phone = phone  # Use group ID as-is
    else:
        formatted_phone = format_phone_number(phone)

        if not formatted_phone:
            return {"success": False, "error": "Invalid phone number"}

    # Create log entry
    log = create_message_log(
        phone=phone,
        message=message,
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        notification_rule=notification_rule,
        recipient_name=recipient_name,
        formatted_phone=formatted_phone
    )
    
    # Queue or send immediately based on settings
    if settings.get("queue_enabled"):
        return {"success": True, "queued": True, "log": log.name}
    else:
        return process_message_log(log.name)


def process_message_log(log_name):
    """
    Process a single message log entry - actually send the message
    
    Args:
        log_name: WhatsApp Message Log document name
    
    Returns:
        dict: Result with success status
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    
    try:
        log = frappe.get_doc("WhatsApp Message Log", log_name)
        
        # Only process Pending or Queued messages
        if log.status not in ("Pending", "Queued"):
            return {"success": False, "error": "Message already processed", "status": log.status}
        
        settings = get_settings()
        
        if not settings.get("enabled"):
            log.mark_failed("WhatsApp notifications disabled")
            return {"success": False, "error": "Disabled"}
        
        # Update status to Sending
        log.db_set("status", "Sending")
        frappe.db.commit()
        
        # Build API request
        url = "{}/message/sendText/{}".format(
            settings.get("api_url"),
            settings.get("instance_name")
        )
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "apikey": settings.get("api_key")
        }
        
        # Build payload - escape for JSON (v13 sandbox compatible)
        payload = {
            "number": log.formatted_phone,
            "text": log.message
        }

        
        # Make request using compatible method
        try:
            response = make_http_request(url, method="POST", headers=headers, data=payload)
            
            # Extract message ID from response
            response_id = None
            if isinstance(response, dict):
                response_id = response.get("key", {}).get("id") or response.get("messageId")
            
            log.mark_sent(response_data=response, response_id=response_id)
            
            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "WhatsApp Sent: {} to {}".format(log.name, log.formatted_phone),
                    "WhatsApp Debug"
                )
            
            return {"success": True, "log": log.name, "response_id": response_id}
            
        except Exception as e:
            error_msg = str(e)
            log.mark_failed(error_msg)

            frappe.log_error(
                message=f"{log.name} -> {error_msg}",
                title="WhatsApp Send Failed"
            )

            return {"success": False, "error": error_msg, "log": log.name}
    
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="WhatsApp Process Error"
        )
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def send_test_message(phone, message=None):
    """
    Send a test message to verify configuration
    
    Args:
        phone: Test phone number
        message: Optional custom message
    
    Returns:
        dict: Test result
    """
    if not message:
        message = "Teste de WhatsApp do ERPNext - {}".format(frappe.utils.now())
    
    return send_whatsapp(phone, message, queue=False)


@frappe.whitelist()
def get_notification_stats():
    """
    Get notification statistics for dashboard

    Returns:
        dict: Statistics
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import get_message_stats
    return get_message_stats()


def is_group_id(recipient):
    """
    Check if the recipient is a WhatsApp group ID

    Args:
        recipient: Phone number or group ID

    Returns:
        bool: True if this is a group ID (ends with @g.us)
    """
    return recipient and isinstance(recipient, str) and "@g.us" in recipient


@frappe.whitelist()
def fetch_whatsapp_groups():
    """
    Fetch all WhatsApp groups from Evolution API

    Returns:
        dict: List of groups with id, subject, size or error message
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": _("WhatsApp notifications are disabled")}

    if not settings.get("api_url") or not settings.get("api_key") or not settings.get("instance_name"):
        return {"success": False, "error": _("Evolution API not configured")}

    url = "{}/group/fetchAllGroups/{}?getParticipants=false".format(
        settings.get("api_url"),
        settings.get("instance_name")
    )

    headers = {"apikey": settings.get("api_key")}

    try:
        response = make_http_request(url, method="GET", headers=headers)

        # The response is typically a list of group objects
        groups = []
        if isinstance(response, list):
            for group in response:
                groups.append({
                    "id": group.get("id"),
                    "subject": group.get("subject", "Unknown Group"),
                    "size": group.get("size", 0)
                })
        elif isinstance(response, dict) and response.get("groups"):
            # Alternative response format
            for group in response.get("groups", []):
                groups.append({
                    "id": group.get("id"),
                    "subject": group.get("subject", "Unknown Group"),
                    "size": group.get("size", 0)
                })

        return {"success": True, "groups": groups}

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="WhatsApp Fetch Groups Error"
        )
        return {"success": False, "error": str(e)}
