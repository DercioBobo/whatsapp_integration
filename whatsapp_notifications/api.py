"""
WhatsApp Notifications - Main API Module
Provides the core functionality for sending WhatsApp messages
Compatible with ERPNext v13, v14, and v15
"""
import frappe
from frappe import _
import json


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
            method: 'whatsapp_notifications.api.send_whatsapp',
            args: {
                phone: '841234567',
                message: 'Hello from ERPNext!'
            }
        });
    """
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.utils import format_phone_number
    
    # Validate inputs
    if not phone or not message:
        return {"success": False, "error": _("Phone and message are required")}
    
    # Get settings
    settings = get_settings()
    
    if not settings.get("enabled"):
        return {"success": False, "error": _("WhatsApp notifications are disabled")}
    
    if not settings.get("api_url") or not settings.get("api_key") or not settings.get("instance_name"):
        return {"success": False, "error": _("Evolution API not configured")}
    
    # Format phone number
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
    
    # Send immediately or queue
    if queue and settings.get("queue_enabled"):
        from whatsapp_notifications.api import process_message_log

        frappe.enqueue(
            process_message_log,
            log_name=log.name,
            queue="short"
        )
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
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.utils import format_phone_number
    
    settings = get_settings()
    
    if not settings.get("enabled"):
        return {"success": False, "error": "WhatsApp notifications disabled"}
    
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
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    
    try:
        log = frappe.get_doc("WhatsApp Message Log", log_name)
        
        if log.status not in ("Pending", "Queued"):
            return {"success": False, "error": "Message already processed"}
        
        settings = get_settings()
        
        if not settings.get("enabled"):
            log.mark_failed("WhatsApp notifications disabled")
            return {"success": False, "error": "Disabled"}
        
        # Update status
        log.db_set("status", "Sending")
        
        # Build API request
        url = "{}/message/sendText/{}".format(
            settings.get("api_url"),
            settings.get("instance_name")
        )
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "apikey": settings.get("api_key")
        }
        
        # Build payload - escape for JSON
        # This is v13 sandbox compatible (no json.dumps in request)
        safe_message = log.message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        json_data = '{{"number": "{}", "text": "{}"}}'.format(log.formatted_phone, safe_message)
        
        # Make request
        try:
            from whatsapp_notifications.utils import make_post_request

            response = make_post_request(
                url,
                headers=headers,
                data=json_data
            )

            
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
                "WhatsApp Send Failed ({}): {}".format(log.name, error_msg),
                "WhatsApp Error"
            )
            
            return {"success": False, "error": error_msg, "log": log.name}
    
    except Exception as e:
        frappe.log_error(
            "WhatsApp Process Error: {}".format(str(e)),
            "WhatsApp Error"
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
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import get_message_stats
    return get_message_stats()


# ============================================================
# V13 Sandbox Compatible API Method
# ============================================================
# This section provides a Server Script compatible implementation
# that can be used as an API method in v13's restricted sandbox

def send_whatsapp_v13_sandbox(phone, message, doctype=None, docname=None):
    """
    V13 Sandbox compatible send function
    Use this in Server Scripts (API type)
    
    Server Script Configuration:
    - Type: API
    - Method: send_whatsapp
    - Allow Guest: No
    
    Script Content:
    ```
    phone = frappe.form_dict.get('phone')
    message = frappe.form_dict.get('message')
    doctype = frappe.form_dict.get('doctype')
    docname = frappe.form_dict.get('docname')
    
    if not phone or not message:
        frappe.throw('Phone and message are required')
    
    # Get Evolution API settings
    api_url = frappe.db.get_single_value('Evolution API Settings', 'api_url')
    api_key = frappe.db.get_single_value('Evolution API Settings', 'api_key')
    instance = frappe.db.get_single_value('Evolution API Settings', 'instance_name')
    country_code = frappe.db.get_single_value('Evolution API Settings', 'default_country_code') or '258'
    
    if not api_url or not api_key or not instance:
        frappe.throw('Evolution API not configured')
    
    # Format phone
    phone = str(phone).replace(' ', '').replace('+', '').replace('-', '')
    if len(phone) == 9 and phone.startswith('8'):
        phone = country_code + phone
    
    # Send via Evolution API
    try:
        url = api_url + '/message/sendText/' + instance
        
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'apikey': api_key
        }
        
        # Escape message for JSON (no f-strings in sandbox)
        safe_message = message.replace('\\\\', '\\\\\\\\').replace('"', '\\\\"').replace('\\n', '\\\\n')
        json_data = '{"number": "' + phone + '", "text": "' + safe_message + '"}'
        
        response = frappe.make_post_request(
            url,
            headers=headers,
            data=json_data
        )
        
        frappe.response['message'] = {'success': True}
        
    except Exception as e:
        frappe.log_error('WhatsApp Failed: ' + str(e), 'WhatsApp Error')
        frappe.response['message'] = {'success': False, 'error': str(e)}
    ```
    """
    pass  # This is documentation only
