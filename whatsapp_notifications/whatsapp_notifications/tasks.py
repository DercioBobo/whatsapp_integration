"""
WhatsApp Notifications - Scheduled Tasks
Background processing for message queue and maintenance
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, nowdate, add_days, getdate


def process_pending_messages():
    """
    Process pending messages from the queue
    Called every minute by scheduler
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import get_pending_messages
    from whatsapp_notifications.whatsapp_notifications.api import process_message_log, process_media_message_log

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
                # Check message type to determine which processor to use
                message_type = frappe.db.get_value("WhatsApp Message Log", msg_name, "message_type")

                if message_type in ("Media", "Document"):
                    result = process_media_message_log(msg_name)
                else:
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


def retry_failed_messages():
    """
    Retry failed messages AND recover stale pending/sending messages
    Called every 5 minutes by scheduler

    Handles:
    1. Failed messages that haven't exceeded retry limit
    2. Stale Pending/Queued messages (worker crash recovery)
    3. Stale Sending messages (stuck in transit)
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.api import process_message_log, process_media_message_log

    def process_by_type(msg_name):
        """Process message based on its type"""
        message_type = frappe.db.get_value("WhatsApp Message Log", msg_name, "message_type")
        if message_type in ("Media", "Document"):
            return process_media_message_log(msg_name)
        else:
            return process_message_log(msg_name)

    try:
        settings = get_settings()

        if not settings.get("enabled"):
            return

        max_retries = settings.get("max_retries", 3)
        retry_delay = settings.get("retry_delay_minutes", 5)

        # Calculate cutoff time for stale messages
        cutoff = add_to_date(now_datetime(), minutes=-retry_delay)

        retried = 0
        recovered = 0

        # 1. Get failed messages eligible for retry
        failed_messages = frappe.get_all(
            "WhatsApp Message Log",
            filters={
                "status": "Failed",
                "retry_count": ["<", max_retries],
                "modified": ["<=", cutoff]
            },
            order_by="modified asc",
            limit_page_length=20,
            pluck="name"
        )

        for msg_name in failed_messages:
            try:
                retry_count = frappe.db.get_value("WhatsApp Message Log", msg_name, "retry_count") or 0

                # Reset status and increment retry count
                frappe.db.set_value(
                    "WhatsApp Message Log",
                    msg_name,
                    {
                        "status": "Pending",
                        "retry_count": retry_count + 1,
                        "error_message": None
                    }
                )
                frappe.db.commit()

                # Actually send based on message type
                process_by_type(msg_name)
                retried += 1

            except Exception as e:
                frappe.log_error(
                    "Error retrying message {}: {}".format(msg_name, str(e)),
                    "WhatsApp Retry Error"
                )

        # 2. Recover stale Pending/Queued messages (worker crash recovery)
        stale_pending = frappe.get_all(
            "WhatsApp Message Log",
            filters={
                "status": ["in", ["Pending", "Queued"]],
                "modified": ["<=", cutoff],
                "scheduled_time": ["is", "not set"]  # Not scheduled for future
            },
            order_by="modified asc",
            limit_page_length=20,
            pluck="name"
        )

        for msg_name in stale_pending:
            try:
                process_by_type(msg_name)
                recovered += 1
            except Exception as e:
                frappe.log_error(
                    "Error recovering stale message {}: {}".format(msg_name, str(e)),
                    "WhatsApp Recovery Error"
                )

        # 3. Recover stale Sending messages (stuck in transit > 10 min)
        sending_cutoff = add_to_date(now_datetime(), minutes=-10)
        stale_sending = frappe.get_all(
            "WhatsApp Message Log",
            filters={
                "status": "Sending",
                "modified": ["<=", sending_cutoff]
            },
            order_by="modified asc",
            limit_page_length=10,
            pluck="name"
        )

        for msg_name in stale_sending:
            try:
                retry_count = frappe.db.get_value("WhatsApp Message Log", msg_name, "retry_count") or 0

                if retry_count < max_retries:
                    # Reset to Pending and retry
                    frappe.db.set_value(
                        "WhatsApp Message Log",
                        msg_name,
                        {
                            "status": "Pending",
                            "retry_count": retry_count + 1,
                            "error_message": "Recovered from stale Sending status"
                        }
                    )
                    frappe.db.commit()

                    process_by_type(msg_name)
                    recovered += 1
                else:
                    # Max retries exceeded, mark as failed
                    frappe.db.set_value(
                        "WhatsApp Message Log",
                        msg_name,
                        {
                            "status": "Failed",
                            "error_message": "Max retries exceeded (stuck in Sending)"
                        }
                    )
                    frappe.db.commit()

            except Exception as e:
                frappe.log_error(
                    "Error recovering sending message {}: {}".format(msg_name, str(e)),
                    "WhatsApp Recovery Error"
                )

        if settings.get("enable_debug_logging") and (retried > 0 or recovered > 0):
            frappe.log_error(
                "Retried {} failed, recovered {} stale messages".format(retried, recovered),
                "WhatsApp Debug"
            )

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            "WhatsApp Retry Error: {}".format(str(e)),
            "WhatsApp Retry Error"
        )


def cleanup_old_logs():
    """
    Delete old message logs based on retention settings
    Called daily at 2 AM by scheduler
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log import cleanup_old_logs as do_cleanup
    
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


def process_scheduled_rules():
    """
    Process Days Before / Days After / On Same Day notification rules.
    Runs hourly; only executes if the current hour matches scheduled_rules_run_hour
    (default 7 AM) configured in Evolution API Settings.
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.events import process_rule

    try:
        settings = get_settings()
        if not settings.get("enabled"):
            return

        # Only run at the configured hour
        run_hour = int(settings.get("scheduled_rules_run_hour") or 7)
        if now_datetime().hour != run_hour:
            return

        today = nowdate()

        rules = frappe.get_all(
            "WhatsApp Notification Rule",
            filters={"enabled": 1, "event": ["in", ["Days Before", "Days After", "On Same Day"]]},
            pluck="name"
        )

        if not rules:
            return

        total_processed = 0

        for rule_name in rules:
            try:
                rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)

                if not rule.date_field:
                    continue

                # Calculate which document date value triggers today
                # "Days Before N": send when date_field == today + N
                # "Days After N":  send when date_field == today - N
                # "On Same Day":   send when date_field == today (plus optional prev/next day passes)
                if rule.event == "On Same Day":
                    passes = [
                        # (target_date, template_override_or_None)
                        (today, None),  # main: same day
                    ]
                    if getattr(rule, 'send_previous_day', 0):
                        prev_tpl = getattr(rule, 'previous_day_template', None)
                        if prev_tpl:
                            passes.insert(0, (add_days(today, 1), prev_tpl))
                    if getattr(rule, 'send_next_day', 0):
                        next_tpl = getattr(rule, 'next_day_template', None)
                        if next_tpl:
                            passes.append((add_days(today, -1), next_tpl))
                else:
                    if rule.event == "Days Before":
                        if not rule.days_offset:
                            continue
                        target_doc_date = add_days(today, rule.days_offset)
                    else:
                        if not rule.days_offset:
                            continue
                        target_doc_date = add_days(today, -rule.days_offset)
                    passes = [(target_doc_date, None)]

                # Query documents whose date_field matches and process each pass
                try:
                    meta = frappe.get_meta(rule.document_type)
                    df = meta.get_field(rule.date_field)
                    if not df:
                        continue
                except Exception as e:
                    frappe.log_error(
                        "Scheduled rule {}: error reading meta {}: {}".format(rule_name, rule.document_type, str(e)),
                        "WhatsApp Scheduled Rule Error"
                    )
                    continue

                for target_doc_date, template_override in passes:
                    try:
                        if df.fieldtype == "Datetime":
                            docs = frappe.db.sql("""
                                SELECT name FROM `tab{doctype}`
                                WHERE DATE({field}) = %s
                            """.format(
                                doctype=rule.document_type,
                                field=rule.date_field
                            ), target_doc_date, as_dict=True)
                            doc_names = [d.name for d in docs]
                        else:
                            doc_names = frappe.get_all(
                                rule.document_type,
                                filters={rule.date_field: target_doc_date},
                                pluck="name"
                            )
                    except Exception as e:
                        frappe.log_error(
                            "Scheduled rule {}: error querying {} for {}: {}".format(
                                rule_name, rule.document_type, target_doc_date, str(e)
                            ),
                            "WhatsApp Scheduled Rule Error"
                        )
                        continue

                    # Set template override on rule object (used by render_message)
                    rule._template_override = template_override

                    for docname in doc_names:
                        try:
                            doc = frappe.get_doc(rule.document_type, docname)
                            process_rule(doc, rule, settings)
                            total_processed += 1
                        except Exception as e:
                            frappe.log_error(
                                "Scheduled rule {} failed for {} {}: {}".format(
                                    rule_name, rule.document_type, docname, str(e)
                                ),
                                "WhatsApp Scheduled Rule Error"
                            )

                    rule._template_override = None

            except Exception as e:
                frappe.log_error(
                    "Error loading scheduled rule {}: {}".format(rule_name, str(e)),
                    "WhatsApp Scheduled Rule Error"
                )

        if settings.get("enable_debug_logging"):
            frappe.log_error(
                "Scheduled rules: processed {} documents for {}".format(total_processed, today),
                "WhatsApp Debug"
            )

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            "WhatsApp Scheduled Rules Error: {}".format(str(e)),
            "WhatsApp Scheduled Rules Error"
        )


# ============================================================
# Schedule Monitor API
# ============================================================

@frappe.whitelist()
def get_schedule_monitor_data(from_date=None, to_date=None, rule_name=None):
    """
    Returns scheduled rule data for the monitor page.
    For each Days Before/Days After rule, computes which documents
    will be (or have been) notified within the given date range.
    """
    if not from_date:
        from_date = nowdate()
    if not to_date:
        to_date = add_days(nowdate(), 30)

    filters = {"enabled": 1, "event": ["in", ["Days Before", "Days After", "On Same Day"]]}
    if rule_name:
        filters["name"] = rule_name

    rules = frappe.get_all(
        "WhatsApp Notification Rule",
        filters=filters,
        fields=["name", "rule_name", "document_type", "event", "date_field",
                "days_offset", "recipient_type", "send_once", "enabled",
                "phone_field", "fixed_recipients", "active_days",
                "enable_active_hours", "active_hours_start", "active_hours_end",
                "send_previous_day", "send_next_day"]
    )

    entries = []
    today = nowdate()

    for rule in rules:
        if not rule.get("date_field"):
            continue
        if rule.event in ("Days Before", "Days After") and not rule.get("days_offset"):
            continue
        try:
            meta = frappe.get_meta(rule.document_type)
            df = meta.get_field(rule.date_field)
            if not df:
                continue

            # Compute document date range that covers the requested notification window
            # notification_date = doc_date - days_offset  (Days Before)
            # notification_date = doc_date + days_offset  (Days After)
            # notification_date = doc_date                (On Same Day)
            offset = int(rule.days_offset or 0)
            if rule.event == "On Same Day":
                doc_date_from = from_date
                doc_date_to = to_date
            elif rule.event == "Days Before":
                doc_date_from = add_days(from_date, offset)
                doc_date_to = add_days(to_date, offset)
            else:
                doc_date_from = add_days(from_date, -offset)
                doc_date_to = add_days(to_date, -offset)

            if df.fieldtype == "Datetime":
                docs = frappe.db.sql("""
                    SELECT name, {field} AS doc_date FROM `tab{doctype}`
                    WHERE DATE({field}) BETWEEN %s AND %s
                    ORDER BY {field} ASC
                    LIMIT 200
                """.format(doctype=rule.document_type, field=rule.date_field),
                    (doc_date_from, doc_date_to), as_dict=True)
            else:
                docs = frappe.get_all(
                    rule.document_type,
                    filters={rule.date_field: ["between", [doc_date_from, doc_date_to]]},
                    fields=["name", rule.date_field + " as doc_date"],
                    order_by=rule.date_field + " asc",
                    limit=200
                )

            # Pre-fetch all sent logs for this rule in the period (one query)
            sent_logs = frappe.get_all(
                "WhatsApp Message Log",
                filters={
                    "notification_rule": rule.name,
                    "reference_doctype": rule.document_type,
                },
                fields=["reference_name", "status", "sent_at", "creation"],
                order_by="creation desc"
            )
            sent_map = {}
            for log in sent_logs:
                if log.reference_name not in sent_map:
                    sent_map[log.reference_name] = log

            for doc in docs:
                raw_date = doc.get("doc_date")
                if not raw_date:
                    continue
                doc_date_str = str(raw_date)[:10]

                if rule.event == "On Same Day":
                    notif_date = doc_date_str
                elif rule.event == "Days Before":
                    notif_date = add_days(doc_date_str, -offset)
                else:
                    notif_date = add_days(doc_date_str, offset)

                log = sent_map.get(doc.name)
                if log:
                    if log.status in ("Sent", "Delivered", "Read"):
                        status = "Sent"
                    elif log.status == "Failed":
                        status = "Failed"
                    elif log.status in ("Pending", "Queued", "Sending"):
                        status = "Queued"
                    else:
                        status = log.status
                elif notif_date == today:
                    status = "Today"
                elif notif_date < today:
                    status = "Overdue"
                else:
                    status = "Upcoming"

                entries.append({
                    "rule": rule.name,
                    "rule_label": rule.rule_name or rule.name,
                    "document_type": rule.document_type,
                    "document_name": doc.name,
                    "event": rule.event,
                    "days_offset": offset,
                    "date_field": rule.date_field,
                    "doc_date": doc_date_str,
                    "notification_date": notif_date,
                    "status": status,
                    "sent_at": log.sent_at if log else None,
                })

        except Exception as e:
            frappe.log_error(
                "Schedule monitor error for rule {}: {}".format(rule.name, str(e)),
                "WhatsApp Schedule Monitor"
            )

    entries.sort(key=lambda x: x["notification_date"])

    # Summary counts
    summary = {"total": len(entries), "today": 0, "upcoming": 0,
               "sent": 0, "overdue": 0, "failed": 0, "queued": 0}
    for e in entries:
        s = e["status"]
        if s == "Today":
            summary["today"] += 1
        elif s == "Upcoming":
            summary["upcoming"] += 1
        elif s == "Sent":
            summary["sent"] += 1
        elif s == "Overdue":
            summary["overdue"] += 1
        elif s == "Failed":
            summary["failed"] += 1
        elif s == "Queued":
            summary["queued"] += 1

    return {
        "rules": rules,
        "entries": entries,
        "summary": summary,
        "from_date": from_date,
        "to_date": to_date,
        "today": today,
    }


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
        "whatsapp_notifications.whatsapp_notifications.tasks.process_pending_messages",
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
        "whatsapp_notifications.whatsapp_notifications.tasks.retry_failed_messages",
        queue="short",
        now=True
    )
    return {"status": "triggered"}


@frappe.whitelist()
def trigger_scheduled_rules():
    """
    Manually trigger processing of Days Before/After scheduled rules
    """
    frappe.enqueue(
        "whatsapp_notifications.whatsapp_notifications.tasks.process_scheduled_rules",
        queue="long",
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
        "whatsapp_notifications.whatsapp_notifications.tasks.cleanup_old_logs",
        queue="long",
        now=True
    )
    return {"status": "triggered"}
