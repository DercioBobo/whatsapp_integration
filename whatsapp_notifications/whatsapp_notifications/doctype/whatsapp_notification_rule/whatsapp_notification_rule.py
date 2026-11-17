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
        self.validate_recurring()
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

        # Validate phone_field and group_mention_fields (comma-separated, dot-notation supported)
        doc_level_fields = []
        if self.phone_field and not self.use_child_table:
            doc_level_fields.extend(self.phone_field.split(","))
        if self.group_mention_fields:
            doc_level_fields.extend(self.group_mention_fields.split(","))
        if doc_level_fields:
            for field in [f.strip() for f in doc_level_fields if f.strip()]:
                if "." in field or "[" in field:
                    # Links and child tables: customer.mobile_no, sales_team.sales_person.employee.cell_number
                    try:
                        ok, msg = resolve_field_path(self.document_type, field)
                    except Exception as e:
                        ok, msg = False, str(e)
                    if not ok:
                        warnings.append(_("Field '{0}': {1}").format(field, msg))
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

    def validate_recurring(self):
        if self.event != "Recurring":
            return

        from whatsapp_notifications.whatsapp_notifications.recurring import parse_filters, get_matching_docnames

        if not self.recurring_frequency:
            frappe.throw(_("Frequency is required for Recurring rules"))
        if self.recurring_frequency == "Weekly" and not self.recurring_day_of_week:
            frappe.throw(_("Day of Week is required for Weekly frequency"))
        if self.recurring_frequency == "Monthly":
            if not self.recurring_day_of_month or not 1 <= self.recurring_day_of_month <= 31:
                frappe.throw(_("Day of Month must be between 1 and 31"))
        if (self.recurring_max_reminders or 0) < 0:
            frappe.throw(_("Max Reminders cannot be negative"))

        # Optional date field: must be a Date/Datetime when given
        if self.date_field and self.document_type:
            df = frappe.get_meta(self.document_type).get_field(self.date_field)
            if not df or df.fieldtype not in ("Date", "Datetime"):
                frappe.throw(_("Date Field '{}' must be a Date or Datetime field of {}").format(
                    self.date_field, self.document_type))
        if not self.date_field:
            self.recurring_start_after_date = 0

        # Filters: valid JSON and a query that actually runs
        # Checks JSON, fields, operators and timespans with a readable error
        parse_filters(self.recurring_filters, self.document_type)
        if self.document_type:
            try:
                get_matching_docnames(self, limit=1)
            except frappe.ValidationError:
                raise
            except Exception as e:
                frappe.throw(_("Document Filters could not be applied to {}: {}").format(self.document_type, e))

        if not self.recurring_filters:
            frappe.msgprint(
                _("No Document Filters set: every {} will get a reminder on each run.").format(self.document_type),
                indicator="orange", title=_("Recurring Rule")
            )

    def validate_date_event(self):
        if self.event not in ("Days Before", "Days After", "On Same Day"):
            return

        if not self.date_field:
            frappe.throw(_("Date Field is required for Days Before/After/On Same Day events"))

        if self.event in ("Days Before", "Days After"):
            if self.days_offset is None or self.days_offset <= 0:
                frappe.throw(_("Days Offset must be greater than 0 for Days Before/After events"))

        if self.document_type:
            meta = frappe.get_meta(self.document_type)
            df = meta.get_field(self.date_field)
            if not df:
                frappe.throw(_("Date Field '{}' not found in {}").format(self.date_field, self.document_type))
            if df.fieldtype not in ("Date", "Datetime"):
                frappe.throw(_("Date Field '{}' must be Date or Datetime type").format(self.date_field))

    def validate_tags(self):
        """Warn when a template tags a role that no member has."""
        templates = [self.message_template, self.previous_day_template, self.next_day_template]
        if not any(t and _TAG_CALL.search(t) for t in templates):
            return
        is_group = self.recipient_type in ("WhatsApp Group", "Document + Group") and self.group_id
        unknown = unknown_tag_keys(templates, self.get_tag_keys()) if is_group else []
        if unknown:
            frappe.msgprint(
                _("The template tags {0}, but no tagged member has that role. "
                  "Set it in Members to Tag as <code>role: number</code> (or use Select Members to Tag).").format(
                    ", ".join("<b>{}</b>".format(frappe.utils.escape_html(u)) for u in unknown)),
                indicator="orange", title=_("Unknown tag")
            )
        elif not is_group:
            frappe.msgprint(_("Tags only work when sending to a WhatsApp group; they will be left out."),
                            indicator="orange", title=_("Tags"))

    def validate_template(self):
        self.validate_tags()
        dummy_ctx = _make_dummy_render_context()
        for label, template in [
            ("message_template", self.message_template),
            ("owner_message_template", self.owner_message_template),
            ("previous_day_template", self.previous_day_template),
            ("next_day_template", self.next_day_template),
        ]:
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

    def _extra_context(self):
        """Recurring run variables (reminder_number, days_overdue...) when set by the scheduler."""
        return getattr(self, "_recurring_context", None) or {}

    def is_applicable(self, doc, event, check_active_hours=True):
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
            "on_same_day": "On Same Day",
            "recurring": "Recurring",
        }
        if event_map.get(event) != self.event:
            return False

        if self.condition:
            try:
                context = get_template_context(doc)
                context.update(self._extra_context())
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

        if check_active_hours and not self.is_within_active_hours():
            return False

        # Recurring rules repeat by design; their per-day de-duplication lives in recurring.py
        if self.send_once and self.event != "Recurring":
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

    def get_group_mention_map(self, doc):
        """
        Who to @mention in group messages, keyed for {{ tag('key') }}:
            - members picked on the rule: key = their role ("supervisor: 2588...")
              or the number itself when no role was given
            - numbers from document fields: key = the field path ("sales_person.mobile_no")
        Returns an ordered {key: [numbers]}.
        """
        if self.recipient_type not in ("WhatsApp Group", "Document + Group") or not self.group_id:
            return {}

        entries = parse_mention_entries(self.group_mentions)

        if self.group_mention_fields and doc is not None:
            for field in [f.strip() for f in self.group_mention_fields.split(",") if f.strip()]:
                val = get_nested_value(doc, field)
                if val:
                    entries.extend((field, phone) for phone in _split_phone_value(str(val)))

        return build_mention_map(entries)

    def get_group_mentions(self, doc):
        """All numbers to @mention in group messages (de-duplicated)."""
        return mention_numbers(self.get_group_mention_map(doc))

    def get_tag_keys(self):
        """Keys usable in {{ tag('...') }}, for template validation."""
        keys = set(build_mention_map(parse_mention_entries(self.group_mentions), format_numbers=False).keys())
        keys.update(normalize_tag_key(f) for f in (self.group_mention_fields or "").split(",") if f.strip())
        return keys

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
        _override = getattr(self, '_template_override', None)
        if _override and not for_owner:
            template = _override
        elif for_owner and self.owner_message_template:
            template = self.owner_message_template
        else:
            template = self.message_template

        try:
            context = get_template_context(doc)
            context["row"] = row if row is not None else frappe._dict()
            cf = changed_fields if changed_fields is not None else []
            context["changed_fields"] = cf
            context["changed_values"] = {f: getattr(row, f, None) for f in cf} if row else {}
            context["previous_values"] = {f: getattr(row_before, f, None) for f in cf} if row_before else {}
            context["row_before"] = row_before
            mention_map = {} if for_owner else self.get_group_mention_map(doc)
            context["mentions"] = format_mentions(mention_numbers(mention_map))
            context["tag"], context["tags"] = make_tag_helpers(mention_map)
            context.update(self._extra_context())
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
    context["mentions"] = ""
    context["tag"], context["tags"] = make_tag_helpers({})
    context.update({
        "reminder_number": 1, "reminders_sent": 0, "last_sent": None,
        "days_overdue": 0, "days_until": 0,
    })
    return context


def normalize_tag_key(key):
    """'Supervisor ' -> 'supervisor', 'Sales Person.Mobile' -> 'sales_person.mobile'."""
    return re.sub(r"[^a-z0-9_.]+", "_", str(key or "").strip().lower()).strip("_")


def parse_mention_entries(text):
    """
    Parse a 'Members to Tag' field into [(role or None, phone)].
    One entry per line (or comma): "supervisor: 258841234567" or just "258841234567".
    """
    entries = []
    for chunk in re.split(r"[\n,;]+", text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        role = None
        if ":" in chunk:
            role, chunk = chunk.split(":", 1)
            role = role.strip() or None
        for phone in _split_phone_value(chunk.strip()):
            entries.append((role, phone))
    return entries


def build_mention_map(entries, format_numbers=True):
    """[(role or None, phone)] -> ordered {key: [numbers]}; key = role, or the number when no role."""
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number

    mention_map = {}
    for role, phone in entries:
        number = format_phone_number(phone) if format_numbers else re.sub(r"\D", "", phone)
        if not number:
            continue
        key = normalize_tag_key(role) if role else number
        numbers = mention_map.setdefault(key, [])
        if number not in numbers:
            numbers.append(number)
    return mention_map


def mention_numbers(mention_map):
    """All numbers in a mention map, de-duplicated, in order."""
    out = []
    for numbers in (mention_map or {}).values():
        for n in numbers:
            if n not in out:
                out.append(n)
    return out


def make_tag_helpers(mention_map):
    """
    Template helpers for placing individual tags:
        {{ tag('supervisor') }}   -> "@258841234567"  (all numbers for that role)
        {{ tag('841234567') }}    -> the member with that number
        {{ tags.supervisor }}     -> same, as a dict
    Unknown roles render as "" (and are flagged when the template is saved).
    """
    tags = {key: format_mentions(numbers) for key, numbers in (mention_map or {}).items()}

    def tag(key):
        found = tags.get(normalize_tag_key(key))
        if found is not None:
            return found
        digits = re.sub(r"\D", "", str(key or ""))
        if len(digits) >= 6:
            for n in mention_numbers(mention_map):
                if n == digits or n.endswith(digits):
                    return format_mentions([n])
        return ""

    return tag, tags


_TAG_CALL = re.compile(r"""tag\(\s*['"]([^'"]+)['"]\s*\)|tags\.([A-Za-z0-9_]+)""")


def unknown_tag_keys(templates, known_keys):
    """Roles used via tag('x') / tags.x in templates that have no member."""
    known = {normalize_tag_key(k) for k in known_keys}
    unknown = []
    for template in templates:
        for m in _TAG_CALL.finditer(template or ""):
            raw = m.group(1) or m.group(2)
            key = normalize_tag_key(raw)
            digits = re.sub(r"\D", "", raw)
            if key in known or (len(digits) >= 6 and any(k.endswith(digits) for k in known)):
                continue
            if raw not in unknown:
                unknown.append(raw)
    return unknown


def format_mentions(numbers):
    """Render numbers as WhatsApp tags: '@258841234567 @258821234567'."""
    return " ".join("@{}".format(n) for n in (numbers or []))


def apply_mentions_to_text(text, numbers):
    """
    WhatsApp only highlights a tag when '@<number>' appears in the text.
    If the template didn't place the tags itself (via {{ mentions }}),
    append the missing ones at the end of the message.
    """
    if not numbers:
        return text
    text = text or ""
    missing = [n for n in numbers if "@{}".format(n) not in text]
    if not missing:
        return text
    tags = format_mentions(missing)
    return "{}\n\n{}".format(text.rstrip(), tags) if text.strip() else tags


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


def _read(obj, field):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _load_linked(obj, field, link_value):
    """Follow a Link / Dynamic Link field to the linked record (None if missing)."""
    doctype = _read(obj, "doctype")
    if not doctype or not link_value or not isinstance(link_value, str):
        return None
    df = frappe.get_meta(doctype).get_field(field)
    if not df:
        return None
    if df.fieldtype == "Link":
        target = df.options
    elif df.fieldtype == "Dynamic Link":
        target = _read(obj, df.options)
    else:
        return None
    if not target:
        return None
    try:
        return frappe.get_cached_doc(target, link_value)
    except frappe.DoesNotExistError:
        return None


def get_nested_value(doc, field_path):
    """
    Read a dotted path from a document, following links and child tables:
        contact_mobile                                   field on the document
        customer.mobile_no                               field on the linked Customer
        sales_team.sales_person.employee.cell_number    every row of a child table,
                                                         through two links
        sales_team[0].sales_person                       one row of a child table
    A path through a child table can give several values; they are returned
    comma-separated (phone fields are split on commas).
    """
    if not field_path:
        return None

    values = _walk(doc, field_path.split("."))
    values = [v for v in values if v not in (None, "")]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    seen = []
    for v in values:
        if str(v) not in seen:
            seen.append(str(v))
    return ", ".join(seen)


def _walk(obj, parts):
    if obj is None:
        return []
    if not parts:
        return [obj]

    part, rest = parts[0], parts[1:]
    index = None
    if "[" in part:
        part, idx = part.split("[", 1)
        try:
            index = int(idx.rstrip("]"))
        except ValueError:
            return []

    value = _read(obj, part)

    # Child table: one row by index, or every row
    if isinstance(value, (list, tuple)):
        rows = value
        if index is not None:
            rows = [value[index]] if len(value) > index else []
        out = []
        for row in rows:
            out.extend(_walk(row, rest))
        return out

    if not rest:
        return [value]

    # More parts after a plain value: it must be a link to follow
    linked = _load_linked(obj, part, value)
    return _walk(linked, rest) if linked is not None else []


_PHONEISH = ("phone", "mobile", "cell", "whatsapp", "contact_no", "telefone", "telemovel")


def _is_phone_field(df):
    name = (df.fieldname or "").lower()
    return df.fieldtype == "Phone" or (
        df.fieldtype == "Data" and (df.options == "Phone" or any(p in name for p in _PHONEISH)))


def resolve_field_path(doctype, field_path):
    """
    Check a dotted path against the schema (links and child tables).
    Returns (ok, message).
    """
    if not field_path:
        return False, _("Empty field")
    meta = frappe.get_meta(doctype)
    parts = field_path.split(".")
    for i, raw in enumerate(parts):
        part = raw.split("[", 1)[0]
        df = meta.get_field(part)
        if not df:
            if part in ("name", "owner", "modified_by") and i == len(parts) - 1:
                return True, ""
            return False, _("'{0}' not found in {1}").format(part, meta.name)
        if i == len(parts) - 1:
            return True, ""
        if df.fieldtype in ("Table", "Table MultiSelect") and df.options:
            meta = frappe.get_meta(df.options)
        elif df.fieldtype == "Link" and df.options:
            meta = frappe.get_meta(df.options)
        elif df.fieldtype == "Dynamic Link":
            return True, ""  # target doctype is only known per document
        else:
            return False, _("'{0}' in {1} is not a link or table, so it can't be followed").format(part, meta.name)
    return True, ""


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
            "on_same_day": "On Same Day",
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

    # Deeper phone paths through child tables and people links, e.g.
    # sales_team.sales_person.employee.cell_number (Sales Team › Sales Person › Employee › Cell Number)
    seen = {f["value"] for f in fields}
    for path, label in _phone_paths(meta):
        if path not in seen:
            seen.add(path)
            fields.append({"value": path, "label": "{} (Phone)".format(label)})

    return fields


# Links are only followed into these when looking for phone numbers several hops away
_PEOPLE_DOCTYPES = frozenset({
    "User", "Employee", "Customer", "Supplier", "Contact", "Lead", "Prospect", "Sales Person",
    "Sales Partner", "Driver", "Student", "Guardian", "Member", "Patient", "Shareholder", "Volunteer",
})


def _phone_paths(meta, prefix="", label_prefix="", hops=0, visited=None, max_hops=3, limit=200):
    """Phone-like fields reachable through child tables and people links (2+ levels deep)."""
    visited = set(visited or ()) | {meta.name}
    out = []
    for df in meta.fields:
        if len(out) >= limit:
            break
        path = prefix + df.fieldname
        label = label_prefix + (df.label or df.fieldname)
        if hops >= 1 and _is_phone_field(df):
            out.append((path, label))
        if hops >= max_hops:
            continue
        target = None
        if df.fieldtype == "Table" and df.options:
            target = df.options
        elif df.fieldtype == "Link" and df.options in _PEOPLE_DOCTYPES:
            target = df.options
        if target and target not in visited:
            try:
                child_meta = frappe.get_meta(target)
            except Exception:
                continue
            out.extend(_phone_paths(child_meta, path + ".", label + " › ", hops + 1, visited,
                                    max_hops, limit - len(out)))
    return out


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

    from whatsapp_notifications.whatsapp_notifications.api import strip_mentions_from_text

    if rule.event == "Recurring":
        from whatsapp_notifications.whatsapp_notifications.recurring import get_recurring_context
        rule._recurring_context = get_recurring_context(rule, doc)

    recipients = rule.get_recipients(doc)
    mentions = rule.get_group_mentions(doc)
    has_group = any(r["type"] == "group" for r in recipients)
    mention_info = {
        "mentions": mentions if has_group else [],
        "mention_everyone": bool(rule.mention_everyone) if has_group else False,
        "mention_names": _get_mention_names(rule, mentions) if has_group else {},
    }

    if rule.use_child_table and rule.child_table:
        row_previews = []
        for r in recipients[:5]:
            msg = rule.render_message(
                doc,
                row=r.get("row"),
                changed_fields=r.get("changed_fields"),
                row_before=r.get("row_before")
            )
            if r["type"] == "group":
                msg = apply_mentions_to_text(msg, mentions)
            row_previews.append({
                "recipient": (rule.group_name or r["value"]) if r["type"] == "group" else r["value"],
                "type": r["type"],
                "row": r.get("row") and getattr(r["row"], "name", None),
                "message": msg,
                # Test Send goes to a single phone, where tags don't apply
                "message_plain": strip_mentions_from_text(msg, mentions)
            })
        result = {
            "row_previews": row_previews,
            "doctype": rule.document_type,
            "docname": docname
        }
        result.update(mention_info)
        return result

    message = rule.render_message(doc)
    formatted_recipients = []
    for r in recipients:
        if r["type"] == "group":
            formatted_recipients.append("{} (Group)".format(rule.group_name or r["value"]))
        else:
            formatted_recipients.append(r["value"])

    if has_group:
        message = apply_mentions_to_text(message, mentions)

    result = {
        "message": message,
        "message_plain": strip_mentions_from_text(message, mentions),
        "recipients": formatted_recipients,
        "doctype": rule.document_type,
        "docname": docname
    }
    result.update(mention_info)
    return result


def _get_mention_names(rule, numbers):
    """
    Best-effort display names for tagged numbers, so the preview can show
    '@John Doe' like WhatsApp does. Never fails the preview.
    """
    if not numbers:
        return {}
    names = {}
    try:
        from whatsapp_notifications.whatsapp_notifications.api import (
            fetch_group_participants, _fill_names_from_contacts
        )
        res = fetch_group_participants(rule.group_id) or {}
        by_number = {p["number"]: p.get("name") for p in res.get("participants") or []}
        for n in numbers:
            if by_number.get(n):
                names[n] = by_number[n]
        # Numbers not found in the group (e.g. from document fields): try Contacts
        missing = [{"number": n, "name": ""} for n in numbers if n not in names]
        _fill_names_from_contacts(missing)
        for p in missing:
            if p["name"]:
                names[p["number"]] = p["name"]
    except Exception:
        pass
    return names
