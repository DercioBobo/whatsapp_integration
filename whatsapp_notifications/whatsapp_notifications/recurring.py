"""
Recurring notification rules

A rule with Event = "Recurring" sends one message per matching document on
every scheduled run (Daily / Weekly / Monthly at a per-rule time). Typical
uses: daily loan penalty updates, weekly due-invoice reminders.

Flow:
    process_recurring_rules()      cron tick (every minute): finds rules that are due
      -> run_recurring_rule()      background job: sends to every eligible document
           -> get_recurring_plan() documents + per-document context / skip reasons
           -> events.process_rule()  existing pipeline (recipients, tags, media, logs)

Safety:
    - A rule runs at most once per day (recurring_last_run).
    - A document never gets two reminders from the same rule on the same day
      (checked against WhatsApp Message Log), so manual "Run Now" and
      scheduler retries can't double-send.
"""
import calendar
import datetime
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, get_datetime, now_datetime, nowdate

RECURRING_EVENT = "Recurring"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Log statuses that count as a delivered (or in-flight) reminder
_COUNTED_STATUSES = ("Pending", "Queued", "Sending", "Sent", "Delivered", "Read")


# ============================================================
# Schedule
# ============================================================

def get_send_time(rule, settings=None):
    """Per-rule send time, falling back to the global scheduled_rules_run_hour."""
    if rule.get("recurring_send_time"):
        t = rule.recurring_send_time
        if isinstance(t, datetime.timedelta):  # Frappe returns Time fields as timedelta
            secs = int(t.total_seconds())
            return datetime.time(secs // 3600 % 24, secs // 60 % 60)
        if isinstance(t, datetime.time):
            return t.replace(second=0, microsecond=0)
        parts = str(t).split(":")
        return datetime.time(int(parts[0]) % 24, int(parts[1]) if len(parts) > 1 else 0)

    if settings is None:
        from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
        settings = get_settings()
    hour = cint(settings.get("scheduled_rules_run_hour") or 7)
    return datetime.time(min(max(hour, 0), 23), 0)


def is_run_day(rule, date):
    """Whether the rule's frequency schedules a run on this date."""
    date = getdate(date)
    freq = rule.get("recurring_frequency") or "Daily"

    if freq == "Daily":
        return True
    if freq == "Weekly":
        return WEEKDAYS[date.weekday()] == rule.get("recurring_day_of_week")
    if freq == "Monthly":
        wanted = cint(rule.get("recurring_day_of_month"))
        if wanted < 1:
            return False
        last_day = calendar.monthrange(date.year, date.month)[1]
        return date.day == min(wanted, last_day)
    return False


def get_next_run(rule, settings=None, from_dt=None):
    """Next datetime the rule will run (today's slot counts if not yet run today)."""
    from_dt = get_datetime(from_dt) if from_dt else now_datetime()
    send_time = get_send_time(rule, settings)
    last_run_date = getdate(rule.recurring_last_run) if rule.get("recurring_last_run") else None

    for i in range(0, 400):
        day = getdate(add_days(from_dt.date(), i))
        if not is_run_day(rule, day):
            continue
        if i == 0 and last_run_date == day:
            continue  # already ran today
        return datetime.datetime.combine(day, send_time)
    return None


def is_due(rule, settings=None, now=None):
    """Due when today is a run day, the send time has passed and it hasn't run today."""
    now = now or now_datetime()
    if not is_run_day(rule, now.date()):
        return False
    if now.time() < get_send_time(rule, settings):
        return False
    if rule.get("recurring_last_run") and getdate(rule.recurring_last_run) == now.date():
        return False
    return True


# ============================================================
# Document selection
# ============================================================

def parse_filters(raw):
    """
    Accept Frappe filters as a JSON list ([[field, op, value], ...] or
    [[doctype, field, op, value], ...]) or a dict ({field: value}).
    """
    if not raw:
        return []
    filters = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(filters, dict):
        return filters
    if not isinstance(filters, list):
        frappe.throw(_("Document Filters must be a JSON list or object"))
    out = []
    for f in filters:
        if not isinstance(f, (list, tuple)) or len(f) not in (3, 4, 5):
            frappe.throw(_("Invalid filter: {0}. Use [field, operator, value].").format(json.dumps(f)))
        # Drop doctype prefix / FilterGroup "hidden" flag
        out.append(list(f[1:4]) if len(f) >= 4 else list(f))
    return out


def _get_filters(rule, today):
    filters = parse_filters(rule.get("recurring_filters"))
    if isinstance(filters, dict):
        filters = [[k, "=", v] if not isinstance(v, (list, tuple)) else [k] + list(v) for k, v in filters.items()]

    if rule.get("recurring_start_after_date") and rule.get("date_field"):
        # date_field + start_days <= today  <=>  date_field < today - start_days + 1
        # ("<" next day also covers Datetime fields with a time part)
        cutoff = add_days(today, -cint(rule.recurring_start_days) + 1)
        filters.append([rule.date_field, "<", cutoff])
        filters.append([rule.date_field, "is", "set"])
    return filters


def get_matching_docnames(rule, today=None, limit=None):
    today = today or nowdate()
    return frappe.get_all(
        rule.document_type,
        filters=_get_filters(rule, today),
        pluck="name",
        order_by="creation asc",
        limit_page_length=limit or 0,
    )


def get_reminder_history(rule_name, doctype, docname):
    """(reminders_sent_so_far, last_sent_datetime, sent_today)"""
    today_start = get_datetime(nowdate())
    row = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT DATE(creation)) AS days_sent,
            MAX(creation) AS last_sent,
            SUM(CASE WHEN creation >= %(today)s THEN 1 ELSE 0 END) AS today_count
        FROM `tabWhatsApp Message Log`
        WHERE notification_rule = %(rule)s
          AND reference_doctype = %(dt)s
          AND reference_name = %(dn)s
          AND status IN %(statuses)s
        """,
        {"rule": rule_name, "dt": doctype, "dn": docname, "today": today_start,
         "statuses": _COUNTED_STATUSES},
        as_dict=True,
    )[0]

    # A failed send today still blocks a second attempt (retry_failed_messages handles it)
    failed_today = frappe.db.exists("WhatsApp Message Log", {
        "notification_rule": rule_name,
        "reference_doctype": doctype,
        "reference_name": docname,
        "status": "Failed",
        "creation": [">=", today_start],
    })
    return cint(row.days_sent), row.last_sent, bool(cint(row.today_count) or failed_today)


def get_recurring_context(rule, doc, history=None, today=None):
    """Extra template variables for recurring messages."""
    today = getdate(today or nowdate())
    sent, last_sent, _sent_today = history or get_reminder_history(rule.name, doc.doctype, doc.name)

    days_overdue = None
    if rule.get("date_field") and doc.get(rule.date_field):
        days_overdue = (today - getdate(doc.get(rule.date_field))).days

    return {
        "reminder_number": sent + 1,
        "reminders_sent": sent,
        "last_sent": last_sent,
        "days_overdue": days_overdue,
        "days_until": -days_overdue if days_overdue is not None else None,
    }


def get_recurring_plan(rule, today=None, limit=None):
    """
    Work out what a run would do, without sending anything.

    Returns:
        dict: {"to_send": [(doc, context)], "skipped": [(docname, reason)], "matched": n}
    """
    today = today or nowdate()
    max_reminders = cint(rule.get("recurring_max_reminders"))
    to_send, skipped = [], []

    names = get_matching_docnames(rule, today)
    for name in names:
        if limit and len(to_send) >= limit:
            break
        history = get_reminder_history(rule.name, rule.document_type, name)
        sent, _last, sent_today = history

        if sent_today:
            skipped.append((name, _("Already reminded today")))
            continue
        if max_reminders and sent >= max_reminders:
            skipped.append((name, _("Reached max reminders ({0})").format(max_reminders)))
            continue

        doc = frappe.get_doc(rule.document_type, name)
        ctx = get_recurring_context(rule, doc, history, today)

        rule._recurring_context = ctx
        try:
            if not rule.is_applicable(doc, "recurring", check_active_hours=False):
                skipped.append((name, _("Condition not met")))
                continue
        finally:
            rule._recurring_context = None

        to_send.append((doc, ctx))

    return {"to_send": to_send, "skipped": skipped, "matched": len(names)}


# ============================================================
# Running
# ============================================================

def process_recurring_rules():
    """
    Scheduler tick (every minute). Enqueues each due rule once per day.
    Cheap: only reads rule rows; document work happens in the background job.
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings

    try:
        settings = get_settings()
        if not settings.get("enabled"):
            return

        rules = frappe.get_all(
            "WhatsApp Notification Rule",
            filters={"enabled": 1, "event": RECURRING_EVENT},
            fields=["name", "recurring_frequency", "recurring_day_of_week",
                    "recurring_day_of_month", "recurring_send_time", "recurring_last_run"],
        )
        now = now_datetime()
        for r in rules:
            if not is_due(r, settings, now):
                continue
            # Mark first so the next tick doesn't enqueue it again
            frappe.db.set_value("WhatsApp Notification Rule", r.name, "recurring_last_run", now,
                                update_modified=False)
            frappe.db.commit()
            frappe.enqueue(
                "whatsapp_notifications.whatsapp_notifications.recurring.run_recurring_rule",
                rule_name=r.name,
                queue="long",
                timeout=3600,
                job_name="whatsapp_recurring_{}".format(r.name),
            )
    except Exception as e:
        frappe.log_error("WhatsApp Recurring Rules Error: {}".format(e), "WhatsApp Recurring Error")


def run_recurring_rule(rule_name):
    """Send this rule's reminders to every eligible document now."""
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.events import process_rule

    settings = get_settings()
    if not settings.get("enabled"):
        return {"sent": 0, "skipped": 0, "error": _("WhatsApp notifications are disabled")}

    rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)
    if rule.event != RECURRING_EVENT:
        return {"sent": 0, "skipped": 0, "error": _("Rule is not Recurring")}

    plan = get_recurring_plan(rule)
    sent = 0
    for doc, ctx in plan["to_send"]:
        rule._recurring_context = ctx
        try:
            process_rule(doc, rule, settings)
            sent += 1
        except Exception as e:
            frappe.log_error(
                "Recurring rule {} failed for {} {}: {}".format(rule_name, doc.doctype, doc.name, e),
                "WhatsApp Recurring Error",
            )
        finally:
            rule._recurring_context = None
        frappe.db.commit()

    if settings.get("enable_debug_logging"):
        frappe.log_error(
            "Recurring rule {}: matched {}, sent {}, skipped {}".format(
                rule_name, plan["matched"], sent, len(plan["skipped"])),
            "WhatsApp Debug",
        )
    return {"sent": sent, "skipped": len(plan["skipped"]), "matched": plan["matched"]}


# ============================================================
# Form actions
# ============================================================

@frappe.whitelist()
def preview_recurring_run(rule_name, limit=10):
    """What the next run would send: schedule, documents, recipients and messages."""
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import (
        apply_mentions_to_text, _get_mention_names
    )

    frappe.has_permission("WhatsApp Notification Rule", "read", throw=True)
    rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)
    if rule.event != RECURRING_EVENT:
        frappe.throw(_("This rule is not Recurring"))

    settings = get_settings()
    limit = min(cint(limit) or 10, 50)
    plan = get_recurring_plan(rule)

    items = []
    mention_names = {}
    for doc, ctx in plan["to_send"][:limit]:
        rule._recurring_context = ctx
        try:
            recipients = rule.get_recipients(doc)
            message = rule.render_message(doc)
            mentions = rule.get_group_mentions(doc)
            has_group = any(r["type"] == "group" for r in recipients)
            if has_group and mentions:
                message = apply_mentions_to_text(message, mentions)
                if not mention_names:
                    mention_names = _get_mention_names(rule, mentions)
        finally:
            rule._recurring_context = None

        items.append({
            "docname": doc.name,
            "reminder_number": ctx["reminder_number"],
            "days_overdue": ctx["days_overdue"],
            "last_sent": ctx["last_sent"],
            "recipients": [
                "{} (Group)".format(rule.group_name or r["value"]) if r["type"] == "group" else r["value"]
                for r in recipients
            ],
            "message": message,
        })

    next_run = get_next_run(rule, settings)
    return {
        "frequency": rule.recurring_frequency,
        "send_time": get_send_time(rule, settings).strftime("%H:%M"),
        "uses_global_time": not rule.get("recurring_send_time"),
        "next_run": next_run,
        "last_run": rule.get("recurring_last_run"),
        "matched": plan["matched"],
        "to_send_count": len(plan["to_send"]),
        "items": items,
        "skipped": [{"docname": n, "reason": r} for n, r in plan["skipped"][:50]],
        "skipped_count": len(plan["skipped"]),
        "mention_names": mention_names,
        "mention_everyone": bool(rule.mention_everyone),
    }


@frappe.whitelist()
def run_recurring_rule_now(rule_name):
    """Manual run from the form. Documents already reminded today are skipped."""
    frappe.has_permission("WhatsApp Notification Rule", "write", throw=True)
    rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)
    if rule.event != RECURRING_EVENT:
        frappe.throw(_("This rule is not Recurring"))

    frappe.enqueue(
        "whatsapp_notifications.whatsapp_notifications.recurring.run_recurring_rule",
        rule_name=rule_name,
        queue="long",
        timeout=3600,
        job_name="whatsapp_recurring_{}".format(rule_name),
    )
    return {"queued": True}
