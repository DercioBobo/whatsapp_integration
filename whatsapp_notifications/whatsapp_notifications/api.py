"""
WhatsApp Notifications - Main API Module
Provides the core functionality for sending WhatsApp messages
Compatible with ERPNext v13, v14, and v15
"""
import frappe
from frappe import _
import base64
import os


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
    except Exception:
        pass  # Fall through to next method

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
    except Exception:
        pass  # Fall through to next method

    # Method 3: requests library (fallback)
    import requests
    if method.upper() == "POST":
        if is_json:
            headers["Content-Type"] = "application/json; charset=utf-8"
            response = requests.post(url, headers=headers, json=data, timeout=60)
        else:
            response = requests.post(url, headers=headers, data=data, timeout=60)
    else:
        response = requests.get(url, headers=headers, timeout=30)

    # Try to get response body for better error messages
    try:
        response_json = response.json()
    except Exception:
        response_json = None

    if not response.ok:
        # Capture the error response from the API
        error_detail = response_json if response_json else response.text[:500]
        raise Exception("API Error {}: {}".format(response.status_code, error_detail))

    return response_json



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

            # Add timeline comment to the referenced document
            if log.reference_doctype and log.reference_name:
                from whatsapp_notifications.whatsapp_notifications.utils import add_notification_sent_comment
                add_notification_sent_comment(
                    log.reference_doctype,
                    log.reference_name,
                    log.formatted_phone,
                    log.recipient_name
                )

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


# ============================================================
# Media Sending Functions
# ============================================================

@frappe.whitelist()
def send_whatsapp_media(phone, doctype=None, docname=None, file_url=None,
                        print_format=None, caption=None, queue=True):
    """
    Send a WhatsApp message with media (document PDF or attachment)

    Args:
        phone: Recipient phone number
        doctype: Reference DocType (required if sending document PDF)
        docname: Reference document name (required if sending document PDF)
        file_url: URL of attached file to send (optional, if not using PDF)
        print_format: Print format for PDF generation (optional)
        caption: Message caption (optional)
        queue: If True, queue for background processing (default)

    Returns:
        dict: Result with success status
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import create_message_log
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number

    # Validate inputs
    if not phone:
        return {"success": False, "error": _("Phone number is required")}

    if not file_url and (not doctype or not docname):
        return {"success": False, "error": _("Either file_url or doctype/docname is required")}

    # Get settings
    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": _("WhatsApp notifications are disabled")}

    if not settings.get("api_url") or not settings.get("api_key") or not settings.get("instance_name"):
        return {"success": False, "error": _("Evolution API not configured")}

    # Format phone number (skip for group IDs)
    if is_group_id(phone):
        formatted_phone = phone
    else:
        formatted_phone = format_phone_number(phone)
        if not formatted_phone:
            return {"success": False, "error": _("Invalid phone number")}

    # Debug logging
    if settings.get("enable_debug_logging"):
        frappe.log_error(
            "send_whatsapp_media called: file_url='{}' (type: {}) | print_format='{}' | doctype={} | docname={}".format(
                file_url, type(file_url).__name__, print_format, doctype, docname
            ),
            "WhatsApp Media API Debug"
        )

    # Determine media type and get file data
    try:
        # Only use file_url if it's a non-empty string
        if file_url and isinstance(file_url, str) and file_url.strip():
            # Sending an attached file
            file_data = get_file_as_base64(file_url)
            if not file_data.get("success"):
                return file_data

            media_base64 = file_data["base64"]
            mimetype = file_data["mimetype"]
            filename = file_data["filename"]
            file_size = file_data.get("size", 0)
            media_type = get_media_type_from_mimetype(mimetype)
            message_type = "Media"
        else:
            # Generate PDF from document
            pdf_data = get_document_pdf(doctype, docname, print_format)
            if not pdf_data.get("success"):
                return pdf_data

            media_base64 = pdf_data["base64"]
            mimetype = "application/pdf"
            filename = pdf_data["filename"]
            file_size = pdf_data.get("size", 0)
            media_type = "document"
            message_type = "Document"

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="WhatsApp Media Preparation Error"
        )
        return {"success": False, "error": str(e)}

    # Build caption if not provided
    if not caption and doctype and docname:
        caption = _("Document: {0}").format(docname)

    # Create message log
    log = create_message_log(
        phone=phone,
        message=caption or "",
        reference_doctype=doctype,
        reference_name=docname,
        formatted_phone=formatted_phone,
        message_type=message_type,
        media_type=media_type,
        file_name=filename,
        file_size=file_size,
        caption=caption
    )

    # Store media data temporarily for processing
    log.db_set("_media_base64", media_base64, update_modified=False)
    log.db_set("_media_mimetype", mimetype, update_modified=False)
    frappe.db.commit()

    # Send immediately or queue based on settings
    if queue and settings.get("queue_enabled"):
        return {"success": True, "message": _("Media message queued"), "log": log.name}
    else:
        result = process_media_message_log(log.name)
        return result


def process_media_message_log(log_name):
    """
    Process a media message log entry - actually send the media

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

        # Get stored media data
        media_base64 = frappe.db.get_value("WhatsApp Message Log", log_name, "_media_base64")
        mimetype = frappe.db.get_value("WhatsApp Message Log", log_name, "_media_mimetype")

        if not media_base64:
            # Try to regenerate the media
            if log.reference_doctype and log.reference_name:
                pdf_data = get_document_pdf(log.reference_doctype, log.reference_name)
                if pdf_data.get("success"):
                    media_base64 = pdf_data["base64"]
                    mimetype = "application/pdf"
                else:
                    log.mark_failed("Could not regenerate media")
                    return {"success": False, "error": "Could not regenerate media"}
            else:
                log.mark_failed("No media data available")
                return {"success": False, "error": "No media data available"}

        # Build API request
        url = "{}/message/sendMedia/{}".format(
            settings.get("api_url"),
            settings.get("instance_name")
        )

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "apikey": settings.get("api_key")
        }

        # Build payload for Evolution API v2.3
        # Evolution API expects raw base64 string, not data URI format
        payload = {
            "number": log.formatted_phone,
            "mediatype": log.media_type or "document",  # image, video, audio, document
            "mimetype": mimetype,
            "caption": log.caption or "",
            "media": media_base64,  # Raw base64 string without data URI prefix
            "fileName": log.file_name or "document.pdf"
        }

        # Debug logging for payload (without the actual base64 data)
        if settings.get("enable_debug_logging"):
            debug_payload = payload.copy()
            debug_payload["media"] = "[BASE64_DATA - {} bytes]".format(len(media_base64))
            frappe.log_error(
                "Sending media to Evolution API:\nURL: {}\nPayload: {}".format(url, debug_payload),
                "WhatsApp Media Debug"
            )

        # Make request
        try:
            response = make_http_request(url, method="POST", headers=headers, data=payload)

            # Extract message ID from response
            response_id = None
            if isinstance(response, dict):
                response_id = response.get("key", {}).get("id") or response.get("messageId")

            log.mark_sent(response_data=response, response_id=response_id)

            # Clean up temporary media data
            frappe.db.set_value("WhatsApp Message Log", log_name, "_media_base64", None, update_modified=False)
            frappe.db.set_value("WhatsApp Message Log", log_name, "_media_mimetype", None, update_modified=False)
            frappe.db.commit()

            # Add timeline comment to the referenced document
            if log.reference_doctype and log.reference_name:
                from whatsapp_notifications.whatsapp_notifications.utils import add_notification_sent_comment
                add_notification_sent_comment(
                    log.reference_doctype,
                    log.reference_name,
                    log.formatted_phone,
                    log.recipient_name
                )

            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    "WhatsApp Media Sent: {} to {}".format(log.name, log.formatted_phone),
                    "WhatsApp Debug"
                )

            return {"success": True, "log": log.name, "response_id": response_id}

        except Exception as e:
            error_msg = str(e)

            # Try to extract more details from the error
            error_details = {
                "error": error_msg,
                "url": url,
                "number": log.formatted_phone,
                "mediatype": log.media_type,
                "mimetype": mimetype,
                "fileName": log.file_name,
                "caption_length": len(log.caption or ""),
                "media_base64_length": len(media_base64) if media_base64 else 0
            }

            log.mark_failed(error_msg)

            frappe.log_error(
                message="{} -> {}\n\nDetails: {}".format(log.name, error_msg, error_details),
                title="WhatsApp Media Send Failed"
            )

            return {"success": False, "error": error_msg, "log": log.name}

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="WhatsApp Media Process Error"
        )
        return {"success": False, "error": str(e)}


def get_document_pdf(doctype, docname, print_format=None):
    """
    Generate PDF from document print format

    Args:
        doctype: Document type
        docname: Document name
        print_format: Print format name (optional, uses Standard if not specified)

    Returns:
        dict: {success: True, base64: "...", filename: "...", size: ...} or error
    """
    try:
        # Get print format
        if not print_format:
            print_format = "Standard"

        # Generate PDF using frappe's print function
        pdf_content = frappe.get_print(
            doctype,
            docname,
            print_format,
            as_pdf=True
        )

        if not pdf_content:
            return {"success": False, "error": _("Could not generate PDF")}

        # Convert to base64
        pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")

        # Generate filename
        filename = "{}-{}.pdf".format(doctype.replace(" ", "-"), docname)

        return {
            "success": True,
            "base64": pdf_base64,
            "filename": filename,
            "size": len(pdf_content)
        }

    except Exception as e:
        error_msg = str(e)

        # Check for wkhtmltopdf error
        if "wkhtmltopdf" in error_msg.lower() or "No wkhtmltopdf" in error_msg:
            user_friendly_error = _(
                "PDF generation requires wkhtmltopdf to be installed on the server. "
                "Please install it or use 'Attached File' option instead."
            )
            frappe.log_error(
                message="wkhtmltopdf not found. Original error: {}".format(error_msg),
                title="WhatsApp PDF Error - wkhtmltopdf Missing"
            )
            return {"success": False, "error": user_friendly_error}

        frappe.log_error(
            message=error_msg,
            title="WhatsApp PDF Generation Error"
        )
        return {"success": False, "error": error_msg}


def get_file_as_base64(file_url):
    """
    Get file content as base64

    Args:
        file_url: File URL (e.g., /files/myfile.pdf or /private/files/myfile.pdf)

    Returns:
        dict: {success: True, base64: "...", filename: "...", mimetype: "...", size: ...} or error
    """
    try:
        # Get file path from URL
        if file_url.startswith("/files/"):
            file_path = frappe.get_site_path("public", "files", file_url.replace("/files/", ""))
        elif file_url.startswith("/private/files/"):
            file_path = frappe.get_site_path("private", "files", file_url.replace("/private/files/", ""))
        else:
            # Try to get from File doctype
            file_doc = frappe.get_doc("File", {"file_url": file_url})
            if file_doc:
                file_path = file_doc.get_full_path()
            else:
                return {"success": False, "error": _("File not found")}

        if not os.path.exists(file_path):
            return {"success": False, "error": _("File not found: {0}").format(file_path)}

        # Read file content
        with open(file_path, "rb") as f:
            file_content = f.read()

        # Get filename
        filename = os.path.basename(file_path)

        # Determine mimetype
        mimetype = get_mimetype(filename)

        # Convert to base64
        file_base64 = base64.b64encode(file_content).decode("utf-8")

        return {
            "success": True,
            "base64": file_base64,
            "filename": filename,
            "mimetype": mimetype,
            "size": len(file_content)
        }

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="WhatsApp File Read Error"
        )
        return {"success": False, "error": str(e)}


def get_mimetype(filename):
    """
    Get mimetype from filename extension

    Args:
        filename: File name with extension

    Returns:
        str: Mimetype
    """
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    mimetypes = {
        # Documents
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain",
        "csv": "text/csv",
        # Images
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        # Videos
        "mp4": "video/mp4",
        "avi": "video/x-msvideo",
        "mov": "video/quicktime",
        "wmv": "video/x-ms-wmv",
        "webm": "video/webm",
        # Audio
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
    }

    return mimetypes.get(ext, "application/octet-stream")


def get_media_type_from_mimetype(mimetype):
    """
    Get Evolution API media type from mimetype

    Args:
        mimetype: File mimetype

    Returns:
        str: Media type (image, video, audio, document)
    """
    if mimetype.startswith("image/"):
        return "image"
    elif mimetype.startswith("video/"):
        return "video"
    elif mimetype.startswith("audio/"):
        return "audio"
    else:
        return "document"


@frappe.whitelist()
def get_document_attachments(doctype, docname):
    """
    Get list of attachments for a document

    Args:
        doctype: Document type
        docname: Document name

    Returns:
        dict: List of attachments with file_url, file_name, file_size
    """
    try:
        attachments = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": doctype,
                "attached_to_name": docname
            },
            fields=["name", "file_name", "file_url", "file_size", "is_private"]
        )

        return {"success": True, "attachments": attachments}

    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_print_formats(doctype):
    """
    Get available print formats for a DocType

    Args:
        doctype: Document type

    Returns:
        dict: List of print format names
    """
    try:
        formats = frappe.get_all(
            "Print Format",
            filters={
                "doc_type": doctype,
                "disabled": 0
            },
            fields=["name"],
            order_by="name"
        )

        # Add Standard option
        result = [{"name": "Standard"}]
        result.extend(formats)

        return {"success": True, "print_formats": result}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Approval Functions
# ============================================================

@frappe.whitelist()
def send_approval(doctype, docname, template_name, phone=None):
    """
    Send an approval request via WhatsApp (manual trigger)

    Args:
        doctype: Document type
        docname: Document name
        template_name: WhatsApp Approval Template name
        phone: Override phone number (optional)

    Returns:
        dict: Result with success status and approval request name
    """
    from whatsapp_notifications.whatsapp_notifications.approval import send_approval_request

    return send_approval_request(doctype, docname, template_name, phone)


@frappe.whitelist()
def cancel_approval(approval_request_name):
    """
    Cancel a pending approval request

    Args:
        approval_request_name: WhatsApp Approval Request name

    Returns:
        dict: Result with success status
    """
    try:
        approval_request = frappe.get_doc("WhatsApp Approval Request", approval_request_name)

        if approval_request.status != "Pending":
            return {
                "success": False,
                "error": _("Cannot cancel - request is not pending (status: {0})").format(
                    approval_request.status
                )
            }

        approval_request.mark_cancelled("Cancelled by user")
        frappe.db.commit()

        return {"success": True, "message": _("Approval request cancelled")}

    except frappe.DoesNotExistError:
        return {"success": False, "error": _("Approval request not found")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_pending_approvals(doctype=None, docname=None):
    """
    Get pending approval requests

    Args:
        doctype: Filter by document type (optional)
        docname: Filter by document name (optional)

    Returns:
        dict: List of pending approval requests
    """
    try:
        filters = {"status": "Pending"}

        if doctype:
            filters["reference_doctype"] = doctype
        if docname:
            filters["reference_name"] = docname

        approvals = frappe.get_all(
            "WhatsApp Approval Request",
            filters=filters,
            fields=[
                "name", "approval_template", "reference_doctype", "reference_name",
                "recipient_phone", "recipient_name", "sent_at", "expires_at"
            ],
            order_by="creation desc"
        )

        return {"success": True, "approvals": approvals}

    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_approval_templates(doctype=None, manual_only=False):
    """
    Get available approval templates

    Args:
        doctype: Filter by document type (optional)
        manual_only: If True, only return templates with manual trigger enabled

    Returns:
        dict: List of approval templates
    """
    try:
        filters = {"enabled": 1}

        if doctype:
            filters["document_type"] = doctype

        if manual_only:
            filters["enable_manual_trigger"] = 1

        templates = frappe.get_all(
            "WhatsApp Approval Template",
            filters=filters,
            fields=["name", "template_name", "document_type", "workflow_state", "enable_manual_trigger"],
            order_by="template_name"
        )

        return {"success": True, "templates": templates}

    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_media_doctype_config(doctype):
    """
    Get WhatsApp media configuration for a DocType

    Args:
        doctype: Document type to check

    Returns:
        dict: Configuration if enabled, or not_enabled flag
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": "WhatsApp notifications disabled"}

    # Check if this doctype is enabled for media
    media_doctypes = settings.get("media_doctypes", [])

    for config in media_doctypes:
        if config.get("document_type") == doctype:
            return {
                "success": True,
                "enabled": True,
                "phone_field": config.get("phone_field"),
                "default_print_format": config.get("default_print_format"),
                "caption_template": config.get("caption_template")
            }

    return {"success": True, "enabled": False}


@frappe.whitelist()
def get_all_media_doctypes():
    """
    Get list of all DocTypes enabled for WhatsApp media button

    Returns:
        dict: List of enabled DocTypes
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "doctypes": []}

    media_doctypes = settings.get("media_doctypes", [])
    doctypes = [config.get("document_type") for config in media_doctypes if config.get("document_type")]

    return {"success": True, "doctypes": doctypes}


@frappe.whitelist()
def clear_all_message_logs():
    """
    Clear all WhatsApp Message Logs

    Returns:
        dict: Success status and count of deleted records
    """
    # Check permission
    if not frappe.has_permission("Evolution API Settings", "write"):
        return {"success": False, "error": "Permission denied"}

    try:
        # Get count before deletion
        count = frappe.db.count("WhatsApp Message Log")

        # Delete all records
        frappe.db.delete("WhatsApp Message Log")
        frappe.db.commit()

        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def clear_all_approval_requests():
    """
    Clear all WhatsApp Approval Requests

    Returns:
        dict: Success status and count of deleted records
    """
    # Check permission
    if not frappe.has_permission("Evolution API Settings", "write"):
        return {"success": False, "error": "Permission denied"}

    try:
        # Get count before deletion
        count = frappe.db.count("WhatsApp Approval Request")

        # Delete all records
        frappe.db.delete("WhatsApp Approval Request")
        frappe.db.commit()

        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_doctype_fields(doctype):
    """
    Get fields from a DocType for field selection

    Args:
        doctype: Document type name

    Returns:
        dict: List of fields with fieldname and label
    """
    try:
        meta = frappe.get_meta(doctype)
        fields = []

        # Field types that can contain phone numbers or be used for updates
        valid_fieldtypes = [
            "Data", "Phone", "Small Text", "Text", "Long Text",
            "Link", "Dynamic Link", "Select", "Int", "Float",
            "Currency", "Check", "Date", "Datetime", "Time"
        ]

        for field in meta.fields:
            if field.fieldtype in valid_fieldtypes and field.fieldname:
                fields.append({
                    "fieldname": field.fieldname,
                    "label": field.label or field.fieldname,
                    "fieldtype": field.fieldtype,
                    "options": field.options
                })

        # Sort by label
        fields.sort(key=lambda x: x.get("label", ""))

        return {"success": True, "fields": fields}
    except Exception as e:
        return {"success": False, "error": str(e)}
