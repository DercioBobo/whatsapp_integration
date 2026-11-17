"""
Document List digests for WhatsApp Auto Report

Turns "a DocType + filters" into WhatsApp text messages:
    - one full digest for the fixed recipients and the WhatsApp group
    - optionally one personal digest per person when "Split by" is set
      (e.g. each salesperson gets only their pending invoices)

Entry points:
    build_digest_messages(report)  -> list of messages (used by send and preview)
    send_digest(report)            -> sends them, returns counts/errors
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, nowdate

ASSIGNED_TO = "_assign"
OWNER = "owner"

# Fields tried, in order, to find a phone on a linked record
PHONE_CANDIDATES = (
    "whatsapp_number", "whatsapp", "mobile_no", "cell_number", "mobile",
    "phone", "phone_no", "contact_mobile", "contact_phone",
)
# Follow these links when the record itself has no phone (e.g. Sales Person -> Employee)
PHONE_VIA_LINKS = ("employee", "user_id", "user", "contact_person", "customer_primary_contact")

_NUMERIC_TYPES = ("Currency", "Float", "Int", "Percent", "Duration")


# ============================================================
# Filters / queries
# ============================================================

def parse_list_filters(raw, doctype=None):
    """Same format as recurring rules (see filters.parse_filters); always a list."""
    from whatsapp_notifications.whatsapp_notifications.filters import parse_filters
    return parse_filters(raw, doctype)


def _safe_order_by(doctype, order_by):
    """Allow only '<field> [asc|desc]' with real fields, to keep raw SQL out of order_by."""
    meta = frappe.get_meta(doctype)
    valid = set(f.fieldname for f in meta.fields) | {"name", "creation", "modified", "owner", "modified_by", "docstatus"}
    parts = []
    for chunk in (order_by or "").split(","):
        tokens = chunk.strip().split()
        if not tokens:
            continue
        field = tokens[0].strip("`")
        direction = tokens[1].lower() if len(tokens) > 1 else "asc"
        if field in valid and direction in ("asc", "desc"):
            parts.append("`tab{}`.`{}` {}".format(doctype, field, direction))
    return ", ".join(parts) or "`tab{}`.`creation` desc".format(doctype)


def _split_filter(split_field, value):
    if split_field == ASSIGNED_TO:
        return [ASSIGNED_TO, "like", '%"{}"%'.format(value.replace("%", "").replace('"', ""))]
    return [split_field, "=", value]


def get_digest_data(report, extra_filters=None):
    """Documents (limited), full count and a total() helper for one digest."""
    doctype = report.list_doctype
    filters = parse_list_filters(report.list_filters) + list(extra_filters or [])
    limit = cint(report.list_limit) if report.list_limit is not None else 20
    meta = frappe.get_meta(doctype)

    count = frappe.db.count(doctype, filters=filters)
    docs = []
    if count and limit != 0:
        docs = frappe.get_all(
            doctype,
            filters=filters,
            fields=["*"],
            order_by=_safe_order_by(doctype, report.list_order_by),
            limit_page_length=max(limit, 0) or 0,
        )

    totals_cache = {}

    def total(fieldname):
        """Sum of a numeric field over *all* matching documents (not just the listed ones)."""
        if fieldname in totals_cache:
            return totals_cache[fieldname]
        df = meta.get_field(fieldname)
        if not df or df.fieldtype not in _NUMERIC_TYPES:
            frappe.throw(_("total('{0}'): not a numeric field of {1}").format(fieldname, doctype))
        res = frappe.get_all(doctype, filters=filters,
                             fields=["sum(`{}`) as total".format(fieldname)])
        totals_cache[fieldname] = (res[0].total if res else 0) or 0
        return totals_cache[fieldname]

    return {
        "docs": docs,
        "count": count,
        "more": max(count - len(docs), 0),
        "total": total,
        "filters": filters,
    }


# ============================================================
# Split by person
# ============================================================

def get_split_options(doctype):
    """Fields that can split a digest: Owner, Assigned To, Link fields and phone-like Data fields."""
    meta = frappe.get_meta(doctype)
    options = [
        {"value": OWNER, "label": _("Created By (User)")},
        {"value": ASSIGNED_TO, "label": _("Assigned To (User)")},
    ]
    for df in meta.fields:
        if df.fieldtype == "Link" and df.options:
            options.append({"value": df.fieldname,
                            "label": "{} ({})".format(df.label or df.fieldname, df.options)})
        elif df.fieldtype == "Phone" or (df.fieldtype == "Data" and (
                df.options == "Phone" or "phone" in df.fieldname or "mobile" in df.fieldname)):
            options.append({"value": df.fieldname,
                            "label": "{} ({})".format(df.label or df.fieldname, _("phone"))})
    return options


def get_split_values(report):
    """Distinct people (split values) among the matching documents."""
    doctype, field = report.list_doctype, report.split_by_field
    filters = parse_list_filters(report.list_filters)

    if field == ASSIGNED_TO:
        values = []
        for row in frappe.get_all(doctype, filters=filters, fields=[ASSIGNED_TO]):
            try:
                for user in json.loads(row.get(ASSIGNED_TO) or "[]"):
                    if user and user not in values:
                        values.append(user)
            except ValueError:
                continue
        return values

    rows = frappe.get_all(doctype, filters=filters + [[field, "is", "set"]],
                          fields=[field], group_by=field)
    return [r.get(field) for r in rows if r.get(field)]


def _split_target_doctype(doctype, field):
    if field in (OWNER, ASSIGNED_TO):
        return "User"
    df = frappe.get_meta(doctype).get_field(field)
    if df and df.fieldtype == "Link":
        return df.options
    return None  # the value itself is a phone


def _find_phone(target_doctype, name, explicit_field=None, depth=0):
    if not name or not frappe.db.exists(target_doctype, name):
        return None
    meta = frappe.get_meta(target_doctype)

    fields = [explicit_field] if explicit_field else [f for f in PHONE_CANDIDATES if meta.has_field(f)]
    if fields:
        values = frappe.db.get_value(target_doctype, name, fields, as_dict=True) or {}
        for f in fields:
            if values.get(f):
                return values[f]

    if depth == 0 and not explicit_field:
        for link in PHONE_VIA_LINKS:
            df = meta.get_field(link)
            if df and df.fieldtype == "Link" and df.options:
                linked = frappe.db.get_value(target_doctype, name, link)
                phone = _find_phone(df.options, linked, depth=1)
                if phone:
                    return phone
    return None


def _display_name(target_doctype, name):
    if not target_doctype:
        return name
    try:
        if target_doctype == "User":
            return frappe.db.get_value("User", name, "full_name") or name
        title_field = frappe.get_meta(target_doctype).title_field
        if title_field:
            return frappe.db.get_value(target_doctype, name, title_field) or name
    except Exception:
        pass
    return name


def resolve_person(report, value):
    """(phone, display_name) for one split value."""
    target = _split_target_doctype(report.list_doctype, report.split_by_field)
    if target is None:
        return value, value
    phone = _find_phone(target, value, (report.split_phone_field or "").strip() or None)
    return phone, _display_name(target, value)


# ============================================================
# Messages
# ============================================================

def _list_link(report, extra_filters=None):
    """
    Desk list URL that opens with exactly the digest's filters applied
    (including the person's own filter for split digests).

    Frappe's list view reads filters from the query string:
        ?status=Unpaid                         -> status = Unpaid
        ?outstanding_amount=[">",0]            -> outstanding_amount > 0
        ?posting_date=["Timespan","this month"]
        ?Sales Invoice Item.item_code=X        -> child-table filter
    A field filtered twice is sent as repeated ["op", value] params.
    """
    from urllib.parse import urlencode, quote

    by_key = {}
    for f in parse_list_filters(report.list_filters) + list(extra_filters or []):
        if len(f) == 4:
            dt, field, op, value = f
            key = field if dt == report.list_doctype else "{}.{}".format(dt, field)
        else:
            (field, op, value), key = f, f[0]
        by_key.setdefault(key, []).append((str(op), value))

    params = []
    for key, conds in by_key.items():
        for op, value in conds:
            if op.strip() == "=" and len(conds) == 1 and not isinstance(value, (list, dict)):
                params.append((key, "" if value is None else str(value)))
            else:
                params.append((key, json.dumps([op, value], ensure_ascii=False, default=str)))

    url = "{}/app/{}".format(frappe.utils.get_url(), frappe.scrub(report.list_doctype).replace("_", "-"))
    # quote (%20), not quote_plus (+): the desk router does not turn '+' back into spaces
    return url + ("?" + urlencode(params, quote_via=quote) if params else "")


def _default_template(report):
    meta = frappe.get_meta(report.list_doctype)
    title = meta.title_field if meta.title_field and meta.title_field != "name" else None
    title_part = " — {{{{ d.{} }}}}".format(title) if title else ""
    return (
        "📋 *{{{{ report_name }}}}*{{% if recipient_name %}} — {{{{ recipient_name }}}}{{% endif %}}\n"
        "{{{{ format_date(date) }}}} · {{{{ count }}}} registo(s)\n\n"
        "{{% for d in docs %}}• {{{{ d.name }}}}{title_part}\n{{% endfor %}}"
        "{{% if more %}}…e mais {{{{ more }}}} — ver todas: {{{{ link }}}}\n"
        "{{% elif show_link %}}\n🔗 {{{{ link }}}}{{% endif %}}"
    ).format(title_part=title_part)


def render_digest(report, data, recipient_name=None, extra_filters=None, mentions=None):
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import (
        get_template_context, format_mentions
    )
    context = get_template_context(None)
    context.pop("doc", None)
    context.update({
        "report_name": report.report_name or report.list_doctype,
        "doctype": report.list_doctype,
        "date": nowdate(),
        "datetime": now_datetime().strftime("%Y-%m-%d %H:%M"),
        "docs": data["docs"],
        "count": data["count"],
        "rows": data["count"],
        "more": data["more"],
        "total": data["total"],
        "recipient_name": recipient_name,
        # Always available (e.g. for "ver mais"); Include Report Link adds it to the
        # default message even when everything fits.
        "link": _list_link(report, extra_filters),
        "show_link": bool(report.include_link),
        "mentions": format_mentions(mentions or []),
    })
    return frappe.render_template(report.message_template or _default_template(report), context)


def _group_mentions(report):
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import _split_phone_value
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    numbers = []
    for phone in _split_phone_value((report.group_mentions or "").replace("\n", ",")):
        formatted = format_phone_number(phone)
        if formatted and formatted not in numbers:
            numbers.append(formatted)
    return numbers


def build_digest_messages(report, split_limit=None):
    """
    Every message a run would send.

    Returns:
        dict: {"messages": [{to, label, kind, message, count, mentions, mention_everyone}],
               "missing_phone": [names], "split_total": n}
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import apply_mentions_to_text

    messages, missing_phone = [], []
    skip_empty = bool(report.send_if_data)

    # Full digest: fixed recipients + group
    fixed = [p.strip() for p in (report.recipients or "").split("\n") if p.strip()]
    if fixed or report.group_id:
        data = get_digest_data(report)
        if data["count"] or not skip_empty:
            for phone in fixed:
                messages.append({"to": phone, "label": phone, "kind": "fixed",
                                 "message": render_digest(report, data), "count": data["count"],
                                 "mentions": [], "mention_everyone": False})
            if report.group_id:
                mentions = _group_mentions(report)
                text = apply_mentions_to_text(render_digest(report, data, mentions=mentions), mentions)
                messages.append({"to": report.group_id, "label": report.group_name or report.group_id,
                                 "kind": "group", "message": text, "count": data["count"],
                                 "mentions": mentions, "mention_everyone": bool(report.mention_everyone)})

    # Personal digests
    split_total = split_remaining = 0
    if report.split_by_field:
        values = get_split_values(report)
        split_total = len(values)
        people = 0
        for i, value in enumerate(values):
            if split_limit and people >= split_limit:
                split_remaining = split_total - i  # not evaluated (preview only)
                break
            phone, name = resolve_person(report, value)
            if not phone:
                missing_phone.append(name or value)
                continue
            extra = [_split_filter(report.split_by_field, value)]
            data = get_digest_data(report, extra)
            if not data["count"]:
                continue
            messages.append({"to": phone, "label": "{} ({})".format(name, phone) if name != phone else phone,
                             "kind": "person", "message": render_digest(report, data, name, extra),
                             "count": data["count"], "mentions": [], "mention_everyone": False})
            people += 1

    return {"messages": messages, "missing_phone": missing_phone,
            "split_total": split_total, "split_remaining": split_remaining}


def send_digest(report):
    """Send all digest messages for this Auto Report. Returns counts/errors."""
    from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification

    built = build_digest_messages(report)
    sent, errors = 0, []

    for m in built["messages"]:
        try:
            result = send_whatsapp_notification(
                phone=m["to"],
                message=m["message"],
                reference_doctype="WhatsApp Auto Report",
                reference_name=report.name,
                recipient_name=m["label"],
                mentions=m["mentions"],
                mention_everyone=m["mention_everyone"],
            )
            if result.get("success") or result.get("queued"):
                sent += 1
            else:
                errors.append("{}: {}".format(m["label"], result.get("error", "Unknown error")))
        except Exception as e:
            errors.append("{}: {}".format(m["label"], e))

    for name in built["missing_phone"]:
        errors.append(_("{0}: no phone number found").format(name))

    return {"sent": sent, "errors": errors, "total": len(built["messages"])}
