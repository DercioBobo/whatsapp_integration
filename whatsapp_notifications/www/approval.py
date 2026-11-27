"""
Approval page: /approval?t=<token>

Opened from the link in a WhatsApp approval message, without login. GET only
renders; the response is submitted by the page's buttons via POST to
approval.submit_approval_response.
"""
import re

import frappe
from frappe.utils import escape_html, format_datetime

from whatsapp_notifications.whatsapp_notifications.approval import get_approval_page_state

no_cache = 1
sitemap = 0


def get_context(context):
    context.no_cache = 1
    context.no_breadcrumbs = 1
    context.page_lang = getattr(frappe.local, "lang", None) or "en"

    token = (frappe.form_dict.get("t") or "").strip()
    state = get_approval_page_state(token)

    context.update(state)
    context.token = token if state.get("state") == "pending" else ""
    context.summary_html = whatsapp_to_html(state.get("summary") or "")
    context.resolved_message_html = whatsapp_to_html(state.get("resolved_message") or "")
    context.csrf_token = (getattr(frappe.session, "data", None) or {}).get("csrf_token") or ""

    for key in ("responded_at", "expires_at", "resolved_at"):
        value = state.get(key)
        context[key + "_display"] = format_datetime(value) if value else ""

    return context


def whatsapp_to_html(text):
    """Escape, then render WhatsApp *bold* / _italic_ / ~strike~ markers"""
    html = escape_html(text)
    html = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<strong>\1</strong>", html)
    html = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<em>\1</em>", html)
    html = re.sub(r"(?<!\w)~(?!\s)(.+?)(?<!\s)~(?!\w)", r"<s>\1</s>", html)
    return html
