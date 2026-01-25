"""
WhatsApp Notifications - Scheduled Tasks
Background processing for message queue and maintenance
"""
import frappe
from frappe import _


def process_pending_messages():
    """
    Process pending messages from the queue
    Called every minute by scheduler
    """
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import get_pending_messages
    from whatsapp_notifications.api import process_message_log
    
    try:
        settings = get_settings()
        
        if not settings.get("enabled"):
            return
        
        # Get pending messages
        messages = get_pending_messages(limit=50)
        
        if not messages:
            return
        
        # Rate limiting
        rate_limit = None
        if settings.get("enable_rate_limiting"):
            rate_limit = settings.get("messages_per_minute", 20)
        
        processed = 0
        
        for msg_name in messages:
            # Check rate limit
            if rate_limit and processed >= rate_limit:
                if settings.get("enable_debug_logging"):
                    frappe.log_error(
                        "Rate limit reached: {} messages".format(processed),
                        "WhatsApp Rate Limit"
                    )
                break
            
            try:
                result = process_message_log(msg_name)
                processed += 1
                
                # Small delay between messages to avoid overwhelming the API
                if processed < len(messages):
                    import time
                    time.sleep(0.5)
                    
            except Exception as e:
                frappe.log_error(
                    "Error processing message {}: {}".format(msg_name, str(e)),
                    "WhatsApp Process Error"
                )
        
        if settings.get("enable_debug_logging") and processed > 0:
            frappe.log_error(
                "Processed {} pending messages".format(processed),
                "WhatsApp Debug"
            )
        
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(
            "WhatsApp Queue Error: {}".format(str(e)),
            "WhatsApp Queue Error"
        )

from frappe.utils import now_datetime, add_to_date

def retry_failed_messages():
    """
    Retry failed messages that haven't exceeded retry limit.
    Also retries stale Pending/Queued messages that were never processed.

    Called every 5 minutes by scheduler.
    Compatible with ERPNext/Frappe v13 to v15.
    """
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import get_failed_messages_for_retry
    from whatsapp_notifications.api import process_message_log

    try:
        settings = get_settings()
        if not settings or not settings.get("enabled"):
            return

        limit = 20

        # Retry Failed (your existing function)
        failed_names = get_failed_messages_for_retry(limit=limit) or []

        # Retry stale Pending/Queued (default stale window: 10 minutes)
        stale_minutes = 10
        cutoff = add_to_date(now_datetime(), minutes=-stale_minutes)

        stale_names = frappe.get_all(
            "WhatsApp Message Log",
            filters={
                "status": ["in", ["Pending", "Queued"]],
                "modified": ["<", cutoff],
            },
            pluck="name",
            limit=limit,
            order_by="modified asc",
        ) or []

        # Merge unique
        to_process = []
        seen = {}
        for n in failed_names + stale_names:
            if n and not seen.get(n):
                to_process.append(n)
                seen[n] = 1

        if not to_process:
            return

        retried = 0

        for msg_name in to_process:
            try:
                row = frappe.db.get_value(
                    "WhatsApp Message Log",
                    msg_name,
                    ["status", "retry_count"],
                    as_dict=1
                ) or {}

                current_status = row.get("status")
                retry_count = row.get("retry_count") or 0

                if current_status not in ("Failed", "Pending", "Queued"):
                    continue

                # Set fields individually (reliable across v13-v15)
                frappe.db.set_value("WhatsApp Message Log", msg_name, "status", "Pending")
                frappe.db.set_value("WhatsApp Message Log", msg_name, "retry_count", retry_count + 1)
                frappe.db.set_value("WhatsApp Message Log", msg_name, "error_message", None)

                # Commit before processing
                frappe.db.commit()

                result = process_message_log(msg_name)

                # If process returns failure without raising, mark failed
                if isinstance(result, dict) and not result.get("success"):
                    latest = frappe.db.get_value("WhatsApp Message Log", msg_name, "status")
                    if latest in ("Pending", "Sending"):
                        frappe.db.set_value("WhatsApp Message Log", msg_name, "status", "Failed")
                        frappe.db.set_value(
                            "WhatsApp Message Log",
                            msg_name,
                            "error_message",
                            result.get("error") or "Unknown error"
                        )
                        frappe.db.commit()

                retried += 1

            except Exception as e:
                frappe.log_error(
                    "Error retrying message " + str(msg_name) + ": " + str(e),
                    "WhatsApp Retry Error"
                )
                try:
                    latest = frappe.db.get_value("WhatsApp Message Log", msg_name, "status")
                    if latest in ("Pending", "Sending"):
                        frappe.db.set_value("WhatsApp Message Log", msg_name, "status", "Failed")
                        frappe.db.set_value("WhatsApp Message Log", msg_name, "error_message", str(e))
                        frappe.db.commit()
                except Exception:
                    pass

        if settings.get("enable_debug_logging") and retried > 0:
            frappe.log_error(
                "Retried " + str(retried) + " messages (Failed + stale Pending/Queued)",
                "WhatsApp Debug"
            )

    except Exception as e:
        frappe.log_error(
            "WhatsApp Retry Error: " + str(e),
            "WhatsApp Retry Error"
        )


def cleanup_old_logs():
    """
    Delete old message logs based on retention settings
    Called daily at 2 AM by scheduler
    """
    from whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import cleanup_old_logs as do_cleanup
    
    try:
        settings = get_settings()
        
        retention_days = settings.get("log_retention_days", 30)
        
        if retention_days <= 0:
            # Keep forever
            return
        
        deleted = do_cleanup(days=retention_days)
        
        if deleted > 0:
            frappe.log_error(
                "Cleaned up {} old WhatsApp message logs".format(deleted),
                "WhatsApp Cleanup"
            )
        
    except Exception as e:
        frappe.log_error(
            "WhatsApp Cleanup Error: {}".format(str(e)),
            "WhatsApp Cleanup Error"
        )


# ============================================================
# Manual Trigger Functions
# ============================================================

@frappe.whitelist()
def trigger_pending_processing():
    """
    Manually trigger processing of pending messages
    Can be called from admin interface
    """
    frappe.enqueue(
        "whatsapp_notifications.tasks.process_pending_messages",
        queue="short",
        now=True
    )
    return {"status": "triggered"}


@frappe.whitelist()
def trigger_retry_processing():
    """
    Manually trigger retry of failed messages
    Can be called from admin interface
    """
    frappe.enqueue(
        "whatsapp_notifications.tasks.retry_failed_messages",
        queue="short",
        now=True
    )
    return {"status": "triggered"}


@frappe.whitelist()
def trigger_cleanup():
    """
    Manually trigger log cleanup
    Can be called from admin interface
    """
    frappe.enqueue(
        "whatsapp_notifications.tasks.cleanup_old_logs",
        queue="long",
        now=True
    )
    return {"status": "triggered"}
