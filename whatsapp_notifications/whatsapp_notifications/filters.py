"""
Document filters typed by users (Recurring rules, Document List reports)

Accepted, from most to least explicit:
    [["posting_date", "Timespan", "this month"], ["docstatus", "=", 1]]
    [["Sales Invoice Item", "item_code", "=", "X"]]      # child-table filter
    ["posting_date", "Timespan", "this month"]           # one filter, no outer list
    {"status": "Unpaid", "outstanding_amount": [">", 0]}

Always returns a list of [field, operator, value] or [doctype, field, operator, value].
Errors say which filter is wrong and show a correct example.
"""
import json

import frappe
from frappe import _

OPERATORS = (
    "=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in",
    "is", "between", "timespan", "descendants of", "not descendants of",
    "ancestors of", "not ancestors of", "descendants of (inclusive)",
)
TIMESPANS = (
    "yesterday", "today", "tomorrow",
    "last week", "this week", "next week",
    "last month", "this month", "next month",
    "last quarter", "this quarter", "next quarter",
    "last 6 months", "next 6 months",
    "last year", "this year", "next year",
)
STANDARD_FIELDS = frozenset({
    "name", "owner", "creation", "modified", "modified_by", "docstatus",
    "idx", "parent", "parentfield", "parenttype", "_assign", "_user_tags",
    "_comments", "_liked_by",
})
EXAMPLE = '[["posting_date", "Timespan", "this month"], ["docstatus", "=", 1]]'


def _fail(msg):
    frappe.throw(msg + "<br><br>" + _("Example: <code>{0}</code>").format(frappe.utils.escape_html(EXAMPLE)),
                 title=_("Invalid Document Filters"))


def _is_single_filter(value):
    """["field", "op", value] written without the outer list."""
    return (isinstance(value, list) and len(value) in (3, 4)
            and all(isinstance(v, str) for v in value[:2])
            and not any(isinstance(v, list) for v in value[:2]))


def parse_filters(raw, doctype=None):
    """
    Normalise user filters to a list. With `doctype`, also check fields,
    operators and timespan values so mistakes surface on save.
    """
    if not raw or (isinstance(raw, str) and not raw.strip()):
        return []

    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError as e:
            _fail(_("Document Filters is not valid JSON ({0}). Check quotes, commas and brackets.").format(e))
    else:
        value = raw

    if isinstance(value, dict):
        value = [[k] + list(v) if isinstance(v, (list, tuple)) else [k, "=", v] for k, v in value.items()]
    elif _is_single_filter(value):
        value = [value]
    elif not isinstance(value, list):
        _fail(_("Document Filters must be a list of filters."))

    out = []
    for i, f in enumerate(value, start=1):
        if not isinstance(f, (list, tuple)) or len(f) not in (3, 4, 5):
            _fail(_("Filter #{0} should look like [\"field\", \"operator\", \"value\"], got: <code>{1}</code>").format(
                i, frappe.utils.escape_html(json.dumps(f, ensure_ascii=False))))
        f = list(f[:4]) if len(f) >= 4 else list(f)  # drop the filter editor's trailing "hidden" flag

        # [doctype, field, op, value] keeps its doctype (child-table filters need it)
        if len(f) == 4:
            target_doctype, field, op, val = f
        else:
            target_doctype, (field, op, val) = doctype, f

        if not isinstance(field, str) or not isinstance(op, str):
            _fail(_("Filter #{0}: field and operator must be text.").format(i))

        op_l = op.strip().lower()
        if op_l not in OPERATORS:
            _fail(_("Filter #{0}: unknown operator '{1}'. Use one of: {2}").format(
                i, op, ", ".join(OPERATORS[:13])))
        if op_l == "timespan" and str(val).strip().lower() not in TIMESPANS:
            _fail(_("Filter #{0}: '{1}' is not a timespan. Use one of: {2}").format(
                i, val, ", ".join(TIMESPANS)))
        if op_l == "is" and str(val).strip().lower() not in ("set", "not set"):
            _fail(_("Filter #{0}: operator 'is' takes \"set\" or \"not set\".").format(i))
        if op_l in ("in", "not in", "between") and not isinstance(val, (list, str)):
            _fail(_("Filter #{0}: '{1}' needs a list, e.g. [\"A\", \"B\"].").format(i, op))

        if target_doctype and field not in STANDARD_FIELDS and "." not in field:
            if not frappe.db.exists("DocType", target_doctype):
                _fail(_("Filter #{0}: DocType '{1}' does not exist.").format(i, target_doctype))
            if not frappe.get_meta(target_doctype).has_field(field):
                _fail(_("Filter #{0}: field '{1}' not found in {2}.").format(i, field, target_doctype))

        out.append(f)
    return out
