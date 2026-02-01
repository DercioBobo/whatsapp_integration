"""
WhatsApp Notification Rule - Defines when and how to send WhatsApp notifications
"""
import frappe
from frappe.model.document import Document
from frappe import _
import json


class WhatsAppNotificationRule(Document):
    """
    Notification Rule Configuration
    Defines triggers, conditions, recipients, and message templates
    """
    
    def validate(self):
        """Validate rule configuration"""
        self.validate_document_type()
        self.validate_phone_field()
        self.validate_template()
        self.validate_condition()
        self.validate_time_settings()
    
    def validate_document_type(self):
        """Ensure document type exists"""
        if self.document_type and not frappe.db.exists("DocType", self.document_type):
            frappe.throw(_("Document Type '{}' does not exist").format(self.document_type))
    
    def validate_phone_field(self):
        """Validate phone field exists in DocType"""
        if self.phone_field and self.document_type:
            meta = frappe.get_meta(self.document_type)
            if not meta.has_field(self.phone_field):
                frappe.msgprint(
                    _("Warning: Field '{}' not found in {}. Make sure it exists or is a child table field.").format(
                        self.phone_field, self.document_type
                    ),
                    indicator="orange"
                )
    
    def validate_template(self):
        """Test template syntax"""
        if self.message_template:
            try:
                # Test render with dummy data
                test_context = {"doc": frappe._dict({"name": "TEST"}), "frappe": frappe}
                frappe.render_template(self.message_template, test_context)
            except Exception as e:
                frappe.throw(_("Invalid message template: {}").format(str(e)))
        
        if self.owner_message_template:
            try:
                test_context = {"doc": frappe._dict({"name": "TEST"}), "frappe": frappe}
                frappe.render_template(self.owner_message_template, test_context)
            except Exception as e:
                frappe.throw(_("Invalid owner message template: {}").format(str(e)))
    
    def validate_condition(self):
        """Test condition syntax"""
        if self.condition:
            try:
                # Test render with dummy data
                test_context = {"doc": frappe._dict({"name": "TEST", "status": "Test"}), "frappe": frappe}
                result = frappe.render_template(self.condition, test_context)
                # Result should be truthy/falsy
            except Exception as e:
                frappe.throw(_("Invalid condition: {}").format(str(e)))
    
    def validate_time_settings(self):
        """Validate active hours settings"""
        import re

        # If active hours restriction is not enabled, clear the time fields
        if not self.enable_active_hours:
            self.active_hours_start = None
            self.active_hours_end = None
            return

        # If enabled, both times are required
        if not self.active_hours_start or not self.active_hours_end:
            frappe.throw(_("Both Active Hours Start and End must be set when 'Restrict to Active Hours' is enabled"))

        # Validate time format (HH:MM or HH:MM:SS)
        time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])(:[0-5][0-9])?$')

        if not time_pattern.match(self.active_hours_start):
            frappe.throw(_("Active Hours Start must be in HH:MM format (e.g., 09:00)"))

        if not time_pattern.match(self.active_hours_end):
            frappe.throw(_("Active Hours End must be in HH:MM format (e.g., 18:00)"))

        # Normalize to HH:MM:SS format
        if len(self.active_hours_start) == 5:
            self.active_hours_start = self.active_hours_start + ":00"
        if len(self.active_hours_end) == 5:
            self.active_hours_end = self.active_hours_end + ":00"
    
    def on_update(self):
        """Clear cache when rules change"""
        clear_rules_cache()
    
    def on_trash(self):
        """Clear cache when rule deleted"""
        clear_rules_cache()
    
    def is_applicable(self, doc, event):
        """
        Check if this rule should fire for the given document and event
        
        Args:
            doc: The document being processed
            event: The event type (after_insert, on_update, etc.)
        
        Returns:
            bool: True if rule should fire
        """
        # Check if enabled
        if not self.enabled:
            return False
        
        # Check document type
        if doc.doctype != self.document_type:
            return False
        
        # Check event matches
        event_map = {
            "after_insert": "After Insert",
            "on_update": "On Update",
            "on_submit": "On Submit",
            "on_cancel": "On Cancel",
            "on_change": "On Change",
            "on_trash": "On Trash"
        }
        if event_map.get(event) != self.event:
            return False
        
        # Check condition if set
        if self.condition:
            try:
                context = get_template_context(doc)
                result = frappe.render_template(self.condition, context)
                # Convert string result to boolean
                if isinstance(result, str):
                    result = result.strip().lower() not in ("", "false", "0", "none", "null")
                if not result:
                    return False
            except Exception as e:
                frappe.log_error(
                    "Rule condition error ({}): {}".format(self.rule_name, str(e)),
                    "WhatsApp Rule Condition Error"
                )
                return False
        
        # Check value changed for On Change event
        if self.event == "On Change" and self.value_changed:
            if not doc.has_value_changed(self.value_changed):
                return False
        
        # Check time restrictions
        if not self.is_within_active_hours():
            return False
        
        # Check send once
        if self.send_once:
            if has_sent_for_rule(self.name, doc.doctype, doc.name):
                return False
        
        return True
    
    def is_within_active_hours(self):
        """Check if current time is within active hours"""
        from frappe.utils import now_datetime
        import datetime

        # If active hours restriction is not enabled, allow all times
        if not self.enable_active_hours:
            return True

        # If times aren't set (shouldn't happen if validation passed), allow all times
        if not self.active_hours_start or not self.active_hours_end:
            return True

        try:
            # Parse time strings (format: HH:MM or HH:MM:SS)
            start_parts = self.active_hours_start.split(":")
            end_parts = self.active_hours_end.split(":")

            start = datetime.time(int(start_parts[0]), int(start_parts[1]))
            end = datetime.time(int(end_parts[0]), int(end_parts[1]))
            now = now_datetime().time()

            if start <= end:
                # Normal range (e.g., 09:00 to 18:00)
                return start <= now <= end
            else:
                # Overnight range (e.g., 22:00 to 06:00)
                return now >= start or now <= end
        except (ValueError, IndexError, AttributeError):
            # If parsing fails, allow (don't block notifications due to config error)
            return True

    def get_recipients(self, doc):
        """
        Get recipients for this notification (phone numbers and/or groups)

        Args:
            doc: The source document

        Returns:
            list: List of dicts with type ('phone' or 'group') and value
        """
        recipients = []

        # Get from document field
        if self.recipient_type in ("Field Value", "Both", "Phone and Group") and self.phone_field:
            phone = get_nested_value(doc, self.phone_field)
            if phone:
                recipients.append({"type": "phone", "value": str(phone)})

        # Get fixed recipients
        if self.recipient_type in ("Fixed Number", "Both") and self.fixed_recipients:
            for phone in self.fixed_recipients.split(","):
                phone = phone.strip()
                if phone:
                    recipients.append({"type": "phone", "value": phone})

        # Get group recipient
        if self.recipient_type in ("Group", "Phone and Group") and self.group_id:
            recipients.append({"type": "group", "value": self.group_id})

        # Remove duplicates while preserving order
        seen = set()
        unique_recipients = []
        for r in recipients:
            key = (r["type"], r["value"])
            if key not in seen:
                seen.add(key)
                unique_recipients.append(r)

        return unique_recipients
    
    def render_message(self, doc, for_owner=False):
        """
        Render the message template with document context
        
        Args:
            doc: The source document
            for_owner: If True, use owner template
        
        Returns:
            str: Rendered message
        """
        template = self.owner_message_template if for_owner and self.owner_message_template else self.message_template
        
        try:
            context = get_template_context(doc)
            return frappe.render_template(template, context)
        except Exception as e:
            frappe.log_error(
                "Template render error ({}): {}".format(self.rule_name, str(e)),
                "WhatsApp Template Error"
            )
            return None


def get_template_context(doc):
    """
    Build context for Jinja2 template rendering
    
    Args:
        doc: The source document
    
    Returns:
        dict: Template context
    """
    return {
        "doc": doc,
        "frappe": frappe,
        "nowdate": frappe.utils.nowdate,
        "nowtime": frappe.utils.nowtime,
        "now_datetime": frappe.utils.now_datetime,
        "format_date": frappe.utils.formatdate,
        "format_datetime": frappe.utils.format_datetime,
        "format_currency": frappe.utils.fmt_money,
        "flt": frappe.utils.flt,
        "cint": frappe.utils.cint,
        "cstr": frappe.utils.cstr,
        "get_url": frappe.utils.get_url,
        "_": _
    }


def get_nested_value(doc, field_path):
    """
    Get value from document, supporting nested fields like 'customer.mobile_no'
    or child table fields like 'items[0].item_code'
    
    Args:
        doc: The document
        field_path: Dot-notation field path
    
    Returns:
        The field value or None
    """
    if not field_path:
        return None
    
    parts = field_path.split(".")
    value = doc
    
    for part in parts:
        if value is None:
            return None
        
        # Handle array notation like items[0]
        if "[" in part:
            field_name, index = part.split("[")
            index = int(index.rstrip("]"))
            value = getattr(value, field_name, None)
            if value and isinstance(value, (list, tuple)) and len(value) > index:
                value = value[index]
            else:
                return None
        else:
            value = getattr(value, part, None) if hasattr(value, part) else value.get(part) if isinstance(value, dict) else None
    
    return value


def get_rules_for_doctype(doctype, event):
    """
    Get all applicable rules for a doctype and event
    
    Args:
        doctype: The DocType name
        event: The event type
    
    Returns:
        list: List of WhatsApp Notification Rule documents
    """
    cache_key = "whatsapp_rules_{}_{}".format(doctype, event)
    rules = frappe.cache().get_value(cache_key)
    
    if rules is None:
        event_map = {
            "after_insert": "After Insert",
            "on_update": "On Update",
            "on_submit": "On Submit",
            "on_cancel": "On Cancel",
            "on_change": "On Change",
            "on_trash": "On Trash"
        }
        
        rules = frappe.get_all(
            "WhatsApp Notification Rule",
            filters={
                "enabled": 1,
                "document_type": doctype,
                "event": event_map.get(event, event)
            },
            pluck="name"
        )
        
        frappe.cache().set_value(cache_key, rules, expires_in_sec=60)
    
    return [frappe.get_doc("WhatsApp Notification Rule", r) for r in rules]


def has_sent_for_rule(rule_name, doctype, docname):
    """
    Check if this rule has already sent for this document
    
    Args:
        rule_name: The notification rule name
        doctype: The document type
        docname: The document name
    
    Returns:
        bool: True if already sent
    """
    return frappe.db.exists("WhatsApp Message Log", {
        "notification_rule": rule_name,
        "reference_doctype": doctype,
        "reference_name": docname,
        "status": ["in", ["Sent", "Pending"]]
    })


def clear_rules_cache():
    """Clear all cached rules"""
    # This is called when rules are modified
    frappe.cache().delete_keys("whatsapp_rules_*")


@frappe.whitelist()
def get_doctype_fields(doctype):
    """
    Get fields from a DocType for field selection
    
    Args:
        doctype: The DocType name
    
    Returns:
        list: List of field options
    """
    if not doctype:
        return []
    
    meta = frappe.get_meta(doctype)
    fields = []
    
    for df in meta.fields:
        if df.fieldtype in ("Data", "Phone", "Int", "Link", "Dynamic Link"):
            fields.append({
                "value": df.fieldname,
                "label": "{} ({})".format(df.label or df.fieldname, df.fieldtype)
            })
    
    # Add linked document fields
    for df in meta.fields:
        if df.fieldtype == "Link" and df.options:
            try:
                linked_meta = frappe.get_meta(df.options)
                for ldf in linked_meta.fields:
                    if ldf.fieldtype in ("Data", "Phone", "Int"):
                        fields.append({
                            "value": "{}.{}".format(df.fieldname, ldf.fieldname),
                            "label": "{} > {} ({})".format(df.label, ldf.label or ldf.fieldname, ldf.fieldtype)
                        })
            except Exception:
                pass
    
    return fields


@frappe.whitelist()
def preview_message(rule_name, docname):
    """
    Preview a message for a specific document

    Args:
        rule_name: The notification rule name
        docname: The document to use for preview

    Returns:
        dict: Preview data including rendered message
    """
    rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)
    doc = frappe.get_doc(rule.document_type, docname)

    message = rule.render_message(doc)
    recipients = rule.get_recipients(doc)

    # Format recipients for display
    formatted_recipients = []
    for r in recipients:
        if isinstance(r, dict):
            if r["type"] == "group":
                # Show group name if available
                group_name = rule.group_name or r["value"]
                formatted_recipients.append("{} (Group)".format(group_name))
            else:
                formatted_recipients.append(r["value"])
        else:
            # Legacy format (string)
            formatted_recipients.append(r)

    return {
        "message": message,
        "recipients": formatted_recipients,
        "doctype": rule.document_type,
        "docname": docname
    }
