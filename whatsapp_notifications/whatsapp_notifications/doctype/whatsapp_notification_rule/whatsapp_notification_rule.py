"""
WhatsApp Notification Rule - Defines when and how to send WhatsApp notifications
"""
import re
import frappe
from frappe.model.document import Document
from frappe import _

_METADATA_FIELDS = frozenset({
    "name", "idx", "modified", "creation", "modified_by", "owner",
    "docstatus", "parent", "parentfield", "parenttype", "doctype"
})


class WhatsAppNotificationRule(Document):
    def validate(self):
        self.validate_document_type()
        self.validate_phone_field()
        self.validate_date_event()
        self.validate_template()
        self.validate_condition()
        self.validate_time_settings()

    def validate_document_type(self):
        if self.document_type and not frappe.db.exists("DocType", self.document_type):
            frappe.throw(_("Document Type '{}' does not exist").format(self.document_type))

    def validate_phone_field(self):
        if not self.document_type:
            return

        meta = frappe.get_meta(self.document_type)
        warnings = []

        # Validate phone_field (comma-separated, dot-notation supported)
        if self.phone_field and not self.use_child_table:
            for field in [f.strip() for f in self.phone_field.split(",") if f.strip()]:
                if "." in field:
                    parts = field.split(".", 1)
                    parent_df = meta.get_field(parts[0])
                    if not parent_df or parent_df.fieldtype != "Link" or not parent_df.options:
                        warnings.append(_("Field '{}' not found in {}").format(field, self.document_type))
                    else:
                        try:
                            linked_meta = frappe.get_meta(parent_df.options)
                            if not linked_meta.has_field(parts[1]):
                                warnings.append(_("Field '{}' not found in {}").format(field, self.document_type))
                        except Exception:
                            pass
                elif not meta.has_field(field):
                    warnings.append(_("Field '{}' not found in {}").format(field, self.document_type))

        # Validate child_phone_field and child_watch_fields against child table schema
        if self.use_child_table and self.child_table:
            child_df = meta.get_field(self.child_table)
            if child_df and child_df.options:
                try:
                    child_meta = frappe.get_meta(child_df.options)

                    if self.child_phone_field:
                        for field in [f.strip() for f in self.child_phone_field.split(",") if f.strip()]:
                            if not child_meta.has_field(field):
                                warnings.append(_("Child phone field '{}' not found in {}").format(field, child_df.options))

                    if self.child_watch_fields:
                        for field in [f.strip() for f in self.child_watch_fields.split(",") if f.strip()]:
                            if not child_meta.has_field(field):
                                warnings.append(_("Watch field '{}' not found in {}").format(field, child_df.options))
                except Exception:
                    pass

        if warnings:
            frappe.msgprint(
                "<br>".join(warnings),
                indicator="orange",
                title=_("Field Validation Warnings")
            )

    def validate_date_event(self):
        if self.event not in ("Days Before", "Days After"):
            return

        if not self.date_field:
            frappe.throw(_("Date Field is required for Days Before/After events"))

        if not self.days_offset or self.days_offset <= 0:
            frappe.throw(_("Days Offset must be greater than 0 for Days Before/After events"))

        if self.document_type:
            meta = frappe.get_meta(self.document_type)
            df = meta.get_field(self.date_field)
            if not df:
                frappe.throw(_("Date Field '{}' not found in {}").format(self.date_field, self.document_type))
            if df.fieldtype not in ("Date", "Datetime"):
                frappe.throw(_("Date Field '{}' must be Date or Datetime type").format(self.date_field))

    def validate_template(self):
        dummy_ctx = _make_dummy_render_context()
        for label, template in [("message_template", self.message_template), ("owner_message_template", self.owner_message_template)]:
            if not template:
                continue
            try:
                frappe.render_template(template, dummy_ctx)
            except (frappe.exceptions.DoesNotExistError, frappe.exceptions.ValidationError):
                pass
            except Exception as e:
                # Only reject genuine Jinja2 syntax errors, not runtime errors
                # that occur because the dummy doc lacks real field values.
                # Expressions like "{:,.2f}".format(doc.field) or
                # frappe.utils.fmt_money(doc.field) are valid but may produce
                # different exception types when run against a real document.
                if _is_template_syntax_error(e):
                    frappe.throw(_("Invalid {}: {}").format(label, str(e)))

    def validate_condition(self):
        if not self.condition:
            return
        dummy_ctx = _make_dummy_render_context()
        try:
            frappe.render_template(self.condition, dummy_ctx)
        except (frappe.exceptions.DoesNotExistError, frappe.exceptions.ValidationError):
            pass
        except Exception as e:
            if _is_template_syntax_error(e):
                frappe.throw(_("Invalid condition: {}").format(str(e)))

    def _has_watched_field_changed(self, doc, watched_fields):
        """
        Check if any of the watched fields changed on the document.
        Wraps has_value_changed in try/except so a missing or broken
        implementation never silently blocks notifications.
        """
        for f in watched_fields:
            try:
                if doc.has_value_changed(f):
                    return True
            except AttributeError:
                # has_value_changed not available (older Frappe) – assume changed
                return True
            except Exception:
                # Any other error – assume changed so we don't silently drop
                return True
        return False

    def validate_time_settings(self):
        if not self.enable_active_hours:
            self.active_hours_start = None
            self.active_hours_end = None
            return

        if not self.active_hours_start or not self.active_hours_end:
            frappe.throw(_("Both Active Hours Start and End must be set when 'Restrict to Active Hours' is enabled"))

        time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])(:[0-5][0-9])?$')

        if not time_pattern.match(self.active_hours_start):
            frappe.throw(_("Active Hours Start must be in HH:MM format (e.g., 09:00)"))

        if not time_pattern.match(self.active_hours_end):
            frappe.throw(_("Active Hours End must be in HH:MM format (e.g., 18:00)"))

        if len(self.active_hours_start) == 5:
            self.active_hours_start = self.active_hours_start + ":00"
        if len(self.active_hours_end) == 5:
            self.active_hours_end = self.active_hours_end + ":00"

    def on_update(self):
        clear_rules_cache()

    def on_trash(self):
        clear_rules_cache()

    def is_applicable(self, doc, event):
        if not self.enabled:
            return False

        if doc.doctype != self.document_type:
            return False

        event_map = {
            "after_insert": "After Insert",
            "on_update": "On Update",
            "on_submit": "On Submit",
            "on_cancel": "On Cancel",
            "on_change": "On Change",
            "on_trash": "On Trash",
            "days_before": "Days Before",
            "days_after": "Days After",
        }
        if event_map.get(event) != self.event:
            return False

        if self.condition:
            try:
                context = get_template_context(doc)
                result = frappe.render_template(self.condition, context)
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

        if self.event in ("On Change", "On Update") and self.value_changed:
            watched = [f.strip() for f in self.value_changed.split(",") if f.strip()]
            if watched and not self._has_watched_field_changed(doc, watched):
                return False

        if not self.is_within_active_hours():
            return False

        if self.send_once:
            if has_sent_for_rule(self.name, doc.doctype, doc.name):
                return False

        return True

    def is_within_active_hours(self):
        from frappe.utils import now_datetime
        import datetime

        if not self.enable_active_hours:
            return True

        if not self.active_hours_start or not self.active_hours_end:
            return True

        try:
            start_parts = self.active_hours_start.split(":")
            end_parts = self.active_hours_end.split(":")
            start = datetime.time(int(start_parts[0]), int(start_parts[1]))
            end = datetime.time(int(end_parts[0]), int(end_parts[1]))
            now = now_datetime().time()

            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end
        except (ValueError, IndexError, AttributeError):
            return True

    def get_recipients(self, doc):
        recipients = []
        seen = set()

        def add(r):
            row_name = r.get("row") and getattr(r["row"], "name", None)
            key = (r["type"], r["value"], row_name)
            if key not in seen:
                seen.add(key)
                recipients.append(r)

        if self.use_child_table and self.child_table:
            child_rows = doc.get(self.child_table) or []
            watch_fields = [f.strip() for f in (self.child_watch_fields or "").split(",") if f.strip()] or None
            row_entries = self._build_row_entries(doc, child_rows, watch_fields)

            if self.only_changed_rows:
                row_entries = [
                    (row, cf, prev) for row, cf, prev in row_entries
                    if prev is None or cf
                ]

            if self.row_condition:
                row_entries = self._filter_by_row_condition(doc, row_entries)

            phone_fields = [f.strip() for f in (self.child_phone_field or "").split(",") if f.strip()]

            for row, changed_fields, prev_row in row_entries:
                if self.recipient_type in ("Document Contact", "Document + Fixed", "Document + Group"):
                    for pf in phone_fields:
                        phone_val = getattr(row, pf, None)
                        if phone_val:
                            for phone in _split_phone_value(str(phone_val)):
                                add({"type": "phone", "value": phone, "row": row,
                                     "changed_fields": changed_fields, "row_before": prev_row})

                if self.recipient_type in ("Fixed Numbers", "Document + Fixed") and self.fixed_recipients:
                    for phone in _split_phone_value(self.fixed_recipients):
                        add({"type": "phone", "value": phone, "row": row,
                             "changed_fields": changed_fields, "row_before": prev_row})

        else:
            if self.recipient_type in ("Document Contact", "Document + Fixed", "Document + Group") and self.phone_field:
                for pf in [f.strip() for f in self.phone_field.split(",") if f.strip()]:
                    phone_val = get_nested_value(doc, pf)
                    if phone_val:
                        for phone in _split_phone_value(str(phone_val)):
                            add({"type": "phone", "value": phone, "row": None,
                                 "changed_fields": [], "row_before": None})

            if self.recipient_type in ("Fixed Numbers", "Document + Fixed") and self.fixed_recipients:
                for phone in _split_phone_value(self.fixed_recipients):
                    add({"type": "phone", "value": phone, "row": None,
                         "changed_fields": [], "row_before": None})

        if self.recipient_type in ("WhatsApp Group", "Document + Group") and self.group_id:
            add({"type": "group", "value": self.group_id, "row": None,
                 "changed_fields": [], "row_before": None})

        return recipients

    def _build_row_entries(self, doc, child_rows, watch_fields=None):
        doc_before = doc.get_doc_before_save()
        prev_rows_by_name = {}

        if doc_before:
            for prev_row in (doc_before.get(self.child_table) or []):
                if getattr(prev_row, "name", None):
                    prev_rows_by_name[prev_row.name] = prev_row

        entries = []
        for row in child_rows:
            prev_row = prev_rows_by_name.get(row.name) if getattr(row, "name", None) else None
            changed_fields = []
            if prev_row is not None:
                changed_fields = _get_changed_field_names(row, prev_row, watch_fields)
            entries.append((row, changed_fields, prev_row))

        return entries

    def _filter_by_row_condition(self, doc, row_entries):
        result = []
        for row, changed_fields, prev_row in row_entries:
            try:
                context = get_template_context(doc)
                context["row"] = row
                context["changed_fields"] = changed_fields
                context["changed_values"] = {f: getattr(row, f, None) for f in changed_fields}
                context["previous_values"] = {f: getattr(prev_row, f, None) for f in changed_fields} if prev_row else {}
                context["row_before"] = prev_row
                res = frappe.render_template(self.row_condition, context)
                if isinstance(res, str):
                    res = res.strip().lower() not in ("", "false", "0", "none", "null")
                if res:
                    result.append((row, changed_fields, prev_row))
            except Exception as e:
                frappe.log_error(
                    "Row condition error ({}): {}".format(self.rule_name, str(e)),
                    "WhatsApp Row Condition Error"
                )
        return result

    def render_message(self, doc, for_owner=False, row=None, changed_fields=None, row_before=None):
        template = self.owner_message_template if for_owner and self.owner_message_template else self.message_template

        try:
            context = get_template_context(doc)
            context["row"] = row if row is not None else frappe._dict()
            cf = changed_fields if changed_fields is not None else []
            context["changed_fields"] = cf
            context["changed_values"] = {f: getattr(row, f, None) for f in cf} if row else {}
            context["previous_values"] = {f: getattr(row_before, f, None) for f in cf} if row_before else {}
            context["row_before"] = row_before
            return frappe.render_template(template, context)
        except Exception as e:
            frappe.log_error(
                "Template render error ({}): {}".format(self.rule_name, str(e)),
                "WhatsApp Template Error"
            )
            return None


def _is_template_syntax_error(exc):
    """
    Returns True only if the exception is a genuine Jinja2 template syntax/parse error
    (not a runtime error caused by the dummy validation context lacking real data).
    """
    try:
        import jinja2
        return isinstance(exc, (jinja2.TemplateSyntaxError, jinja2.UndefinedError))
    except ImportError:
        return False


class _DummyValue:
    """
    A permissive dummy value for template validation.
    Acts as 0 (numeric) and "" (string) so Jinja expressions like
    "{:,.2f}".format(doc.field), doc.field | round(2), and
    frappe.utils.fmt_money(doc.field) all pass validation without errors.
    """
    def __float__(self): return 0.0
    def __int__(self): return 0
    def __index__(self): return 0
    def __str__(self): return ""
    def __repr__(self): return ""
    def __bool__(self): return False
    def __format__(self, spec):
        try:
            return format(0.0, spec) if spec else ""
        except Exception:
            return ""
    def __round__(self, n=0): return 0.0
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _DummyValue()
    def __call__(self, *args, **kwargs): return _DummyValue()
    def __getitem__(self, key): return _DummyValue()
    def __iter__(self): return iter([])
    def __len__(self): return 0
    def __add__(self, other): return 0.0
    def __radd__(self, other): return 0.0
    def __sub__(self, other): return 0.0
    def __rsub__(self, other): return 0.0
    def __mul__(self, other): return 0.0
    def __rmul__(self, other): return 0.0
    def __truediv__(self, other): return 0.0
    def __rtruediv__(self, other): return 0.0
    def __lt__(self, other): return True
    def __le__(self, other): return True
    def __gt__(self, other): return False
    def __ge__(self, other): return False
    def __eq__(self, other): return False


class _DummyDoc:
    """
    A mock document for template validation that returns _DummyValue
    for any attribute or key access, making format expressions safe to evaluate.
    """
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _DummyValue()

    def __getitem__(self, key):
        return _DummyValue()

    def get(self, key, default=None):
        return _DummyValue()


def _make_dummy_render_context():
    doc = _DummyDoc()
    row = _DummyDoc()
    context = get_template_context(doc)
    context["row"] = row
    context["changed_fields"] = []
    context["changed_values"] = {}
    context["previous_values"] = {}
    context["row_before"] = None
    return context


def _normalize(val):
    if val is None or val == "":
        return None
    return val


def _get_changed_field_names(row, prev_row, watch_fields=None):
    fields_to_check = watch_fields if watch_fields else [
        k for k in vars(row) if k not in _METADATA_FIELDS and not k.startswith("_")
    ]
    changed = []
    for f in fields_to_check:
        if _normalize(getattr(row, f, None)) != _normalize(getattr(prev_row, f, None)):
            changed.append(f)
    return changed


def _split_phone_value(phone):
    if not phone:
        return []
    normalized = phone.replace(",", "/").replace(";", "/")
    return [p.strip() for p in normalized.split("/") if p.strip()]


def get_template_context(doc):
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
        "_": _,
    }


def get_nested_value(doc, field_path):
    if not field_path:
        return None

    parts = field_path.split(".")
    value = doc

    for part in parts:
        if value is None:
            return None
        if "[" in part:
            field_name, index = part.split("[")
            index = int(index.rstrip("]"))
            value = getattr(value, field_name, None)
            if value and isinstance(value, (list, tuple)) and len(value) > index:
                value = value[index]
            else:
                return None
        else:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict):
                value = value.get(part)
            else:
                return None

    return value


def get_rules_for_doctype(doctype, event):
    cache_key = "whatsapp_rules_{}_{}".format(doctype, event)
    rules = frappe.cache().get_value(cache_key)

    if rules is None:
        event_map = {
            "after_insert": "After Insert",
            "on_update": "On Update",
            "on_submit": "On Submit",
            "on_cancel": "On Cancel",
            "on_change": "On Change",
            "on_trash": "On Trash",
            "days_before": "Days Before",
            "days_after": "Days After",
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
    return frappe.db.exists("WhatsApp Message Log", {
        "notification_rule": rule_name,
        "reference_doctype": doctype,
        "reference_name": docname,
        "status": ["in", ["Sent", "Pending"]]
    })


def clear_rules_cache():
    frappe.cache().delete_keys("whatsapp_rules_*")


@frappe.whitelist()
def get_doctype_fields(doctype):
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

    for df in meta.fields:
        if df.fieldtype == "Link" and df.options:
            try:
                linked_meta = frappe.get_meta(df.options)
                for ldf in linked_meta.fields:
                    if ldf.fieldtype in ("Data", "Phone", "Int"):
                        fields.append({
                            "value": "{}.{}".format(df.fieldname, ldf.fieldname),
                            "label": "{} > {} ({})".format(
                                df.label or df.fieldname, ldf.label or ldf.fieldname, ldf.fieldtype
                            )
                        })
            except Exception:
                pass

    return fields


@frappe.whitelist()
def get_doctype_watch_fields(doctype):
    """Return all watchable fields for On Change / On Update value_changed picker.
    Includes all scalar types (Data, Currency, Float, Int, Select, Date, etc.)
    but excludes layout, Table, and Attach fields.
    """
    if not doctype:
        return []

    _excluded = frozenset({
        "Section Break", "Column Break", "HTML", "Button", "Fold",
        "Heading", "Tab Break", "Table", "Table MultiSelect",
        "Attach", "Attach Image", "HTML Editor", "Text Editor",
        "Geolocation", "Signature", "Barcode",
    })

    meta = frappe.get_meta(doctype)
    fields = []
    for df in meta.fields:
        if df.fieldtype in _excluded:
            continue
        if df.fieldname in _METADATA_FIELDS:
            continue
        fields.append({
            "value": df.fieldname,
            "label": "{} ({})".format(df.label or df.fieldname, df.fieldtype)
        })

    return fields


@frappe.whitelist()
def get_child_tables(doctype):
    if not doctype:
        return []

    meta = frappe.get_meta(doctype)
    result = []
    for df in meta.fields:
        if df.fieldtype == "Table" and df.options:
            result.append({
                "fieldname": df.fieldname,
                "label": df.label or df.fieldname,
                "options": df.options
            })
    return result


@frappe.whitelist()
def get_child_table_fields(doctype, child_table_field, all_fields=False):
    if not doctype or not child_table_field:
        return []

    meta = frappe.get_meta(doctype)
    df = meta.get_field(child_table_field)
    if not df or df.fieldtype != "Table" or not df.options:
        return []

    child_meta = frappe.get_meta(df.options)
    _structural = frozenset({
        "Section Break", "Column Break", "HTML", "Button",
        "Fold", "Heading", "Tab Break"
    })
    _phone_types = frozenset({"Data", "Phone", "Int", "Link", "Dynamic Link"})

    result = []
    for cdf in child_meta.fields:
        if cdf.fieldname in _METADATA_FIELDS:
            continue
        if cdf.fieldtype in _structural:
            continue
        if all_fields or cdf.fieldtype in _phone_types:
            result.append({
                "value": cdf.fieldname,
                "label": "{} ({})".format(cdf.label or cdf.fieldname, cdf.fieldtype)
            })

    return result


@frappe.whitelist()
def get_doctype_date_fields(doctype):
    if not doctype:
        return []

    meta = frappe.get_meta(doctype)
    result = []
    for df in meta.fields:
        if df.fieldtype in ("Date", "Datetime"):
            result.append({
                "value": df.fieldname,
                "label": "{} ({})".format(df.label or df.fieldname, df.fieldtype)
            })
    return result


@frappe.whitelist()
def preview_message(rule_name, docname):
    rule = frappe.get_doc("WhatsApp Notification Rule", rule_name)
    doc = frappe.get_doc(rule.document_type, docname)

    recipients = rule.get_recipients(doc)

    if rule.use_child_table and rule.child_table:
        row_previews = []
        for r in recipients[:5]:
            msg = rule.render_message(
                doc,
                row=r.get("row"),
                changed_fields=r.get("changed_fields"),
                row_before=r.get("row_before")
            )
            row_previews.append({
                "recipient": r["value"],
                "type": r["type"],
                "row": r.get("row") and getattr(r["row"], "name", None),
                "message": msg
            })
        return {
            "row_previews": row_previews,
            "doctype": rule.document_type,
            "docname": docname
        }

    message = rule.render_message(doc)
    formatted_recipients = []
    for r in recipients:
        if r["type"] == "group":
            formatted_recipients.append("{} (Group)".format(rule.group_name or r["value"]))
        else:
            formatted_recipients.append(r["value"])

    return {
        "message": message,
        "recipients": formatted_recipients,
        "doctype": rule.document_type,
        "docname": docname
    }
