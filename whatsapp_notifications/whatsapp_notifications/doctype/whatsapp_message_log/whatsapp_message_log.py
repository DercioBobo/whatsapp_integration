"""
WhatsApp Message Log - Audit trail for all WhatsApp messages
"""
import frappe
from frappe.model.document import Document
from frappe import _
import json


class WhatsAppMessageLog(Document):
    """
    Message Log for tracking all WhatsApp messages
    Provides complete audit trail and retry tracking
    """
    
    def before_insert(self):
        """Set defaults before insert"""
        if not self.status:
            self.status = "Pending"
        if not self.retry_count:
            self.retry_count = 0
    
    @frappe.whitelist()
    def retry_send(self):
        """
        Retry sending a failed message
        """
        if self.status != "Failed":
            frappe.throw(_("Only failed messages can be retried"))

        self.status = "Pending"
        self.retry_count = (self.retry_count or 0) + 1
        self.error_message = None
        self.save(ignore_permissions=True)

        # Trigger immediate send based on message type
        if self.message_type in ("Media", "Document"):
            from whatsapp_notifications.whatsapp_notifications.api import process_media_message_log
            process_media_message_log(self.name)
        else:
            from whatsapp_notifications.whatsapp_notifications.api import process_message_log
            process_message_log(self.name)

        return {"success": True, "message": _("Message queued for retry")}
    
    @frappe.whitelist()
    def cancel_message(self):
        """
        Cancel a pending message
        """
        if self.status not in ("Pending", "Queued"):
            frappe.throw(_("Only pending or queued messages can be cancelled"))
        
        self.status = "Cancelled"
        self.save(ignore_permissions=True)
        
        return {"success": True, "message": _("Message cancelled")}
    
    def mark_sent(self, response_data=None, response_id=None):
        """
        Mark message as sent
        
        Args:
            response_data: API response data
            response_id: Message ID from API
        """
        self.status = "Sent"
        self.sent_at = frappe.utils.now_datetime()
        
        if response_data:
            self.response_data = json.dumps(response_data) if isinstance(response_data, dict) else str(response_data)
        
        if response_id:
            self.response_id = response_id
        
        self.save(ignore_permissions=True)
    
    def mark_failed(self, error_message):
        """
        Mark message as failed
        
        Args:
            error_message: Error description
        """
        self.status = "Failed"
        self.error_message = str(error_message)[:500]  # Limit length
        self.save(ignore_permissions=True)


def create_message_log(phone, message, reference_doctype=None, reference_name=None,
                       notification_rule=None, recipient_name=None, formatted_phone=None,
                       scheduled_time=None, message_type=None, media_type=None,
                       file_name=None, file_size=None, caption=None):
    """
    Create a new message log entry

    Args:
        phone: Original phone number
        message: Message content
        reference_doctype: Source document type
        reference_name: Source document name
        notification_rule: Triggering rule name
        recipient_name: Recipient display name
        formatted_phone: Phone number after formatting
        scheduled_time: When to send (for delayed messages)
        message_type: Type of message (Text, Media, Document)
        media_type: Type of media (image, video, audio, document)
        file_name: Name of the file being sent
        file_size: Size of file in bytes
        caption: Caption for media messages

    Returns:
        WhatsApp Message Log document
    """
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number


    # Format phone if not already formatted
    if not formatted_phone:
        formatted_phone = format_phone_number(phone)

    log = frappe.get_doc({
        "doctype": "WhatsApp Message Log",
        "phone": phone,
        "formatted_phone": formatted_phone,
        "message": message,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "notification_rule": notification_rule,
        "recipient_name": recipient_name,
        "scheduled_time": scheduled_time,
        "status": "Queued" if scheduled_time else "Pending",
        "message_type": message_type or "Text",
        "media_type": media_type,
        "file_name": file_name,
        "file_size": file_size,
        "caption": caption
    })

    log.insert(ignore_permissions=True)
    frappe.db.commit()

    return log


def get_pending_messages(limit=50):
    """
    Get pending messages ready to be sent
    
    Args:
        limit: Maximum number of messages to return
    
    Returns:
        list: List of WhatsApp Message Log names
    """
    now = frappe.utils.now_datetime()
    
    # Build filters for messages ready to send
    messages = frappe.db.sql("""
        SELECT name FROM `tabWhatsApp Message Log`
        WHERE status IN ('Pending', 'Queued')
        AND (scheduled_time IS NULL OR scheduled_time <= %s)
        ORDER BY creation ASC
        LIMIT %s
    """, (now, limit), as_dict=True)
    
    return [m.name for m in messages]


def get_failed_messages_for_retry(limit=20):
    """
    Get failed messages that can be retried
    
    Args:
        limit: Maximum number of messages
    
    Returns:
        list: List of WhatsApp Message Log names
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    
    settings = get_settings()
    max_retries = settings.get("max_retries", 3)
    retry_delay = settings.get("retry_delay_minutes", 5)
    
    # Calculate minimum time since last attempt
    cutoff = frappe.utils.add_to_date(
        frappe.utils.now_datetime(),
        minutes=-retry_delay
    )
    
    return frappe.get_all(
        "WhatsApp Message Log",
        filters={
            "status": "Failed",
            "retry_count": ["<", max_retries],
            "modified": ["<=", cutoff]
        },
        order_by="modified asc",
        limit_page_length=limit,
        pluck="name"
    )


def cleanup_old_logs(days=30):
    """
    Delete old message logs
    
    Args:
        days: Delete logs older than this many days
    
    Returns:
        int: Number of logs deleted
    """
    if days <= 0:
        return 0
    
    cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-days)
    
    old_logs = frappe.get_all(
        "WhatsApp Message Log",
        filters={
            "creation": ["<", cutoff],
            "status": ["in", ["Sent", "Delivered", "Read", "Cancelled", "Failed"]]
        },
        pluck="name"
    )
    
    for log_name in old_logs:
        frappe.delete_doc("WhatsApp Message Log", log_name, ignore_permissions=True)
    
    if old_logs:
        frappe.db.commit()
    
    
    if old_logs:
        frappe.db.commit()
    
    return len(old_logs)


@frappe.whitelist()
def clear_all_logs():
    """
    Clear all message logs
    """
    if not frappe.session.user == "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Not permitted"))
        
    frappe.db.sql("TRUNCATE `tabWhatsApp Message Log`")
    return True



@frappe.whitelist()
def get_message_stats(days=7):
    """
    Get message statistics for dashboard
    
    Args:
        days: Number of days to include
    
    Returns:
        dict: Statistics
    """
    cutoff = frappe.utils.add_to_date(frappe.utils.nowdate(), days=-days)
    
    stats = frappe.db.sql("""
        SELECT 
            status,
            COUNT(*) as count
        FROM `tabWhatsApp Message Log`
        WHERE creation >= %s
        GROUP BY status
    """, cutoff, as_dict=True)
    
    result = {
        "total": 0,
        "sent": 0,
        "failed": 0,
        "pending": 0,
        "by_status": {}
    }
    
    for row in stats:
        result["by_status"][row.status] = row.count
        result["total"] += row.count
        
        if row.status in ("Sent", "Delivered", "Read"):
            result["sent"] += row.count
        elif row.status == "Failed":
            result["failed"] += row.count
        elif row.status in ("Pending", "Queued"):
            result["pending"] += row.count
    
    return result
