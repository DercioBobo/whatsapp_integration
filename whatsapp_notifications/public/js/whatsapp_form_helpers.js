// WhatsApp Notifications - shared form helpers
//
// Loaded through the doctype_js hook (see hooks.py) for the forms that use it,
// so it ships with the form script and never depends on a rebuilt/cached asset.

frappe.whatsapp = frappe.whatsapp || {};

// ============================================================
// Shared form helpers: WhatsApp group picker, member tagging,
// tag rendering and filter editing. Used by WhatsApp Notification
// Rule and WhatsApp Auto Report.
// ============================================================

/**
 * Pick a WhatsApp group into frm fields.
 * opts: { id_field: 'group_id', name_field: 'group_name' }
 */
frappe.whatsapp.pick_group = function(frm, opts) {
    opts = Object.assign({ id_field: 'group_id', name_field: 'group_name' }, opts || {});

    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.fetch_whatsapp_groups',
        freeze: true,
        freeze_message: __('Fetching WhatsApp groups...'),
        callback: function(r) {
            if (!(r.message && r.message.success)) {
                let error = (r.message && r.message.error) || __('Failed to fetch WhatsApp groups');
                if (frm.doc[opts.id_field]) {
                    // Still let the user remove the current group when the API is unreachable
                    frappe.confirm(
                        __('Could not load groups ({0}). Remove the current group "{1}" instead?',
                            [frappe.utils.escape_html(error), frappe.utils.escape_html(frm.doc[opts.name_field] || frm.doc[opts.id_field])]),
                        () => frappe.whatsapp.remove_group(frm, opts)
                    );
                } else {
                    frappe.msgprint({ title: __('Error'), indicator: 'red', message: error });
                }
                return;
            }

            let groups = r.message.groups;
            if (!groups || groups.length === 0) {
                frappe.msgprint(__('No WhatsApp groups found. Make sure your WhatsApp is connected to groups.'));
                return;
            }

            let dialog = new frappe.ui.Dialog({
                title: __('Select WhatsApp Group'),
                fields: [{ fieldname: 'group', fieldtype: 'Select', label: __('Group'), options: groups.map(g => g.id), reqd: 1 }],
                primary_action_label: __('Select'),
                primary_action: function(values) {
                    let selected = groups.find(g => g.id === values.group);
                    if (selected) {
                        frm.set_value(opts.id_field, selected.id);
                        frm.set_value(opts.name_field, selected.subject);
                        dialog.hide();
                        frappe.show_alert({ message: __('Group selected: ') + selected.subject, indicator: 'green' }, 3);
                    }
                },
                // Only offered when a group is already set
                secondary_action_label: frm.doc[opts.id_field] ? __('Remove group') : null,
                secondary_action: frm.doc[opts.id_field] ? function() {
                    dialog.hide();
                    frappe.whatsapp.remove_group(frm, opts);
                } : null
            });

            // Show readable labels instead of raw group IDs
            let $select = dialog.fields_dict.group.$input;
            $select.empty();
            groups.forEach(g => {
                $select.append($('<option></option>').val(g.id).text(`${g.subject} (${g.size} members)`));
            });
            if (frm.doc[opts.id_field]) {
                $select.val(frm.doc[opts.id_field]);
            }
            dialog.show();
        }
    });
};

/** Clear the group fields (the form's group_id handler clears the tagged members). */
frappe.whatsapp.remove_group = function(frm, opts) {
    opts = Object.assign({ id_field: 'group_id', name_field: 'group_name' }, opts || {});
    let name = frm.doc[opts.name_field] || frm.doc[opts.id_field];
    frm.set_value(opts.id_field, '');
    frm.set_value(opts.name_field, '');
    frappe.show_alert({ message: __('Group removed: {0}', [name]), indicator: 'orange' }, 3);
};

frappe.whatsapp.parse_number_list = function(value) {
    return frappe.whatsapp.parse_mention_entries(value).map(e => e.number);
};

/** 'Supervisor ' -> 'supervisor' (same rule as the server's normalize_tag_key). */
frappe.whatsapp.normalize_tag_key = function(key) {
    return String(key || '').trim().toLowerCase().replace(/[^a-z0-9_.]+/g, '_').replace(/^_+|_+$/g, '');
};

/** "supervisor: 258841234567" / "258841234567" lines -> [{role, number}] */
frappe.whatsapp.parse_mention_entries = function(value) {
    let out = [];
    (value || '').split(/[\n,;]+/).forEach(chunk => {
        chunk = chunk.trim();
        if (!chunk) return;
        let role = '';
        let idx = chunk.indexOf(':');
        if (idx >= 0) {
            role = chunk.slice(0, idx).trim();
            chunk = chunk.slice(idx + 1);
        }
        let number = chunk.replace(/\D/g, '');
        if (number) out.push({ role: role, number: number });
    });
    return out;
};

/**
 * Keys usable in {{ tag('...') }} for a form: roles and untagged numbers from the
 * members field, plus document field paths (rules' "Tag From Document Fields").
 * Returns [{key, label, is_role}].
 */
frappe.whatsapp.tag_keys = function(frm, mentions_field, fields_field) {
    let out = [];
    let seen = {};
    frappe.whatsapp.parse_mention_entries(frm.doc[mentions_field]).forEach(e => {
        let key = e.role ? frappe.whatsapp.normalize_tag_key(e.role) : e.number;
        if (!key || seen[key]) return;
        seen[key] = true;
        out.push({ key: key, label: e.role ? `@${e.role} (+${e.number})` : `+${e.number}`, is_role: !!e.role });
    });
    (frm.doc[fields_field] || '').split(',').map(f => f.trim()).filter(Boolean).forEach(f => {
        let key = frappe.whatsapp.normalize_tag_key(f);
        if (!key || seen[key]) return;
        seen[key] = true;
        out.push({ key: key, label: `@${f} (${__('from document')})`, is_role: true });
    });
    return out;
};

/**
 * Pick group members to @mention, each with an optional role so templates can
 * place them individually: {{ tag('supervisor') }}.
 * Saves one line per member: "supervisor: 258841234567" (or just the number).
 * opts: { group_field: 'group_id', group_name_field: 'group_name', mentions_field: 'group_mentions' }
 */
frappe.whatsapp.pick_group_members = function(frm, opts) {
    opts = Object.assign({ group_field: 'group_id', group_name_field: 'group_name', mentions_field: 'group_mentions' }, opts || {});
    let group_id = frm.doc[opts.group_field];

    if (!group_id) {
        frappe.msgprint(__('Select a WhatsApp group first.'));
        return;
    }

    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.fetch_group_participants',
        args: { group_id: group_id },
        freeze: true,
        freeze_message: __('Fetching group members...'),
        callback: function(r) {
            if (!r.message || !r.message.success) {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: (r.message && r.message.error) || __('Failed to fetch group members')
                });
                return;
            }

            let participants = r.message.participants || [];
            if (!participants.length) {
                frappe.msgprint(__('No taggable members found in this group.'));
                return;
            }

            let esc = frappe.utils.escape_html;
            // Match saved numbers by suffix so "841234567" and "258841234567" are the same member
            let same = (a, b) => a === b || a.endsWith(b) || b.endsWith(a);
            let current = frappe.whatsapp.parse_mention_entries(frm.doc[opts.mentions_field]);
            let saved_for = n => current.find(c => same(n, c.number));

            // Numbers saved on the form that are no longer in the group are kept as they are
            let orphans = current.filter(c => !participants.some(p => same(p.number, c.number)));

            let rows = participants.map((p, i) => {
                let saved = saved_for(p.number);
                let label = p.name ? `${esc(p.name)} <span class="text-muted">+${esc(p.number)}</span>` : `+${esc(p.number)}`;
                if (p.admin) label += ` <span class="text-muted small">· ${esc(__('admin'))}</span>`;
                return `
                    <div class="wa-member-row d-flex align-items-center" data-i="${i}" data-search="${esc(((p.name || '') + ' ' + p.number).toLowerCase())}"
                         style="gap:10px;padding:6px 4px;border-bottom:1px solid var(--border-color, #eee);">
                        <input type="checkbox" class="wa-member-check" ${saved ? 'checked' : ''} style="margin:0;">
                        <div style="flex:1;min-width:0;">${label}</div>
                        <input type="text" class="form-control input-xs wa-member-role" value="${esc(saved ? saved.role : '')}"
                               placeholder="${esc(__('role, e.g. supervisor'))}" style="width:170px;">
                    </div>`;
            }).join('');

            let fields = [
                { fieldname: 'search', fieldtype: 'Data', label: __('Search'), placeholder: __('Filter by name or number') },
                { fieldname: 'help', fieldtype: 'HTML', options: `<p class="text-muted small mb-1">${__('Tick who to tag. Give a role to place that person anywhere in the message with {0}.', ["<code>{{ tag('supervisor') }}</code>"])}</p>` },
                { fieldname: 'members', fieldtype: 'HTML', options: `<div class="wa-member-list" style="max-height:380px;overflow:auto;">${rows}</div>` }
            ];
            if (orphans.length) {
                fields.push({
                    fieldname: 'orphans_html', fieldtype: 'HTML',
                    options: `<p class="text-muted small mt-2">${__('Kept (not found in group)')}: ${esc(orphans.map(o => (o.role ? o.role + ': ' : '') + o.number).join(', '))}</p>`
                });
            }
            if (r.message.hidden) {
                fields.push({
                    fieldname: 'hidden_html', fieldtype: 'HTML',
                    options: `<p class="text-muted small">${__('{0} member(s) hide their phone number and cannot be tagged by number.', [r.message.hidden])}</p>`
                });
            }

            let dialog = new frappe.ui.Dialog({
                title: __('Tag Members of {0}', [frm.doc[opts.group_name_field] || group_id]),
                fields: fields,
                size: 'large',
                primary_action_label: __('Save Selection'),
                primary_action: function() {
                    let $list = dialog.$wrapper.find('.wa-member-list');
                    let lines = orphans.map(o => (o.role ? o.role + ': ' : '') + o.number);
                    let roles_seen = {};
                    let duplicate_roles = [];
                    $list.find('.wa-member-row').each(function() {
                        if (!$(this).find('.wa-member-check').prop('checked')) return;
                        let p = participants[$(this).data('i')];
                        let role = ($(this).find('.wa-member-role').val() || '').trim().replace(/[:\n,;]/g, ' ').trim();
                        let key = frappe.whatsapp.normalize_tag_key(role);
                        if (key) {
                            if (roles_seen[key]) duplicate_roles.push(role);
                            roles_seen[key] = true;
                        }
                        lines.push(role ? `${role}: ${p.number}` : p.number);
                    });
                    frm.set_value(opts.mentions_field, lines.join('\n'));
                    dialog.hide();
                    frappe.show_alert({ message: __('{0} member(s) will be tagged', [lines.length]), indicator: 'green' }, 3);
                    if (duplicate_roles.length) {
                        frappe.show_alert({
                            message: __('Several people share the role {0}: tag(...) will tag all of them.', [esc(duplicate_roles.join(', '))]),
                            indicator: 'blue'
                        }, 6);
                    }
                },
                secondary_action_label: __('Clear All'),
                secondary_action: function() {
                    dialog.$wrapper.find('.wa-member-check').prop('checked', false);
                }
            });

            // Typing a role ticks the member
            dialog.$wrapper.on('input', '.wa-member-role', function() {
                if ($(this).val().trim()) {
                    $(this).closest('.wa-member-row').find('.wa-member-check').prop('checked', true);
                }
            });

            dialog.fields_dict.search.$input.on('input', function() {
                let q = ($(this).val() || '').toLowerCase().trim();
                dialog.$wrapper.find('.wa-member-row').each(function() {
                    $(this).toggleClass('d-none', !!q && !String($(this).data('search')).includes(q));
                });
            });

            dialog.show();
        }
    });
};

/**
 * Escape a message and render tags (an at-sign followed by a number) the way
 * WhatsApp shows them: highlighted, with the member's name when known
 * (number kept in the tooltip).
 */
frappe.whatsapp.render_tags = function(message, names) {
    names = names || {};
    let html = frappe.utils.escape_html(message || '');
    return html.replace(/@(\d{6,15})(?!\d)/g, function(match, number) {
        let name = names[number];
        let label = name ? '@' + frappe.utils.escape_html(name) : match;
        return `<span title="+${number}" style="color:#027eb5;font-weight:500;">${label}</span>`;
    });
};

/**
 * Parse stored filters into [[field, op, value] | [doctype, field, op, value], ...].
 * Accepts a single filter without the outer list and {field: value} objects.
 * Returns null when the text can't be understood.
 */
frappe.whatsapp.parse_filters = function(raw) {
    if (!raw || !String(raw).trim()) return [];
    let f;
    try {
        f = JSON.parse(raw);
    } catch (e) {
        return null;
    }
    if (Array.isArray(f)) {
        let single = (f.length === 3 || f.length === 4) && typeof f[0] === 'string' && typeof f[1] === 'string';
        if (single) f = [f];
        if (!f.every(x => Array.isArray(x) && x.length >= 3 && x.length <= 5)) return null;
        return f.map(x => x.length >= 4 ? x.slice(0, 4) : x);
    }
    if (f && typeof f === 'object') {
        return Object.keys(f).map(k => Array.isArray(f[k]) ? [k].concat(f[k]) : [k, '=', f[k]]);
    }
    return null;
};

/**
 * Show a plain-language summary of a filters field under it, e.g.
 * "Sales Invoice where Posting Date is this month · Outstanding Amount > 0".
 * opts: { doctype, field }
 */
frappe.whatsapp.describe_filters = function(frm, opts) {
    let field = frm.get_field(opts.field);
    if (!field) return;
    field.$wrapper.find('.wa-filter-summary').remove();
    if (!opts.doctype) return;

    let $box = $('<div class="wa-filter-summary small" style="margin-top:6px;"></div>');
    field.$wrapper.append($box);

    let filters = frappe.whatsapp.parse_filters(frm.doc[opts.field]);
    if (filters === null) {
        $box.html(`<span class="text-danger">${__('Not valid filters. Use the Edit Filters button, or e.g. {0}',
            ['<code>[["posting_date", "Timespan", "this month"]]</code>'])}</span>`);
        return;
    }
    if (!filters.length) {
        $box.html(`<span class="text-warning">${__('No filters: every {0} matches.', [__(opts.doctype)])}</span>`);
        return;
    }

    let esc = frappe.utils.escape_html;
    let fmt_value = v => Array.isArray(v) ? v.map(x => esc(String(x))).join(', ') : esc(String(v));
    let phrase = function(op, v) {
        switch (String(op).toLowerCase()) {
            case '=': return __('is') + ' <b>' + fmt_value(v) + '</b>';
            case '!=': return __('is not') + ' <b>' + fmt_value(v) + '</b>';
            case 'timespan': return __('is') + ' <b>' + esc(__(String(v))) + '</b>';
            case 'is': return String(v).toLowerCase() === 'set' ? __('is set') : __('is not set');
            case 'in': return __('is one of') + ' <b>' + fmt_value(v) + '</b>';
            case 'not in': return __('is not one of') + ' <b>' + fmt_value(v) + '</b>';
            case 'like': return __('contains') + ' <b>' + fmt_value(String(v).replace(/%/g, '')) + '</b>';
            case 'not like': return __('does not contain') + ' <b>' + fmt_value(String(v).replace(/%/g, '')) + '</b>';
            case 'between': return __('is between') + ' <b>' + fmt_value(v) + '</b>';
            default: return esc(op) + ' <b>' + fmt_value(v) + '</b>';
        }
    };

    frappe.model.with_doctype(opts.doctype, function() {
        let parts = filters.map(f => {
            let dt = f.length === 4 ? f[0] : opts.doctype;
            let fieldname = f.length === 4 ? f[1] : f[0];
            let op = f.length === 4 ? f[2] : f[1];
            let value = f.length === 4 ? f[3] : f[2];
            let label = __(frappe.meta.get_label(dt, fieldname) || fieldname);
            if (dt !== opts.doctype) label = __(dt) + ' › ' + label;
            return esc(label) + ' ' + phrase(op, value);
        });
        $box.html(`<span class="text-muted">${esc(__(opts.doctype))} ${__('where')}</span> ${parts.join(' <span class="text-muted">·</span> ')}`);
    });
};

/**
 * Edit a JSON filters field with Frappe's filter builder.
 * opts: { doctype, field, title }
 */
frappe.whatsapp.edit_filters = function(frm, opts) {
    if (!opts.doctype) {
        frappe.msgprint(__('Select a Document Type first.'));
        return;
    }
    let current = frappe.whatsapp.parse_filters(frm.doc[opts.field]);
    if (current === null) {
        frappe.msgprint(__('The filters are not valid JSON. Fix or clear them before using the editor.'));
        return;
    }

    frappe.model.with_doctype(opts.doctype, function() {
        let filter_group;
        let dialog = new frappe.ui.Dialog({
            title: opts.title || __('Filters'),
            fields: [{ fieldtype: 'HTML', fieldname: 'filter_area' }],
            size: 'large',
            primary_action_label: __('Set Filters'),
            primary_action: function() {
                // Keep the doctype only for child-table filters; plain ones stay [field, op, value]
                let filters = filter_group.get_filters().map(f =>
                    f[0] && f[0] !== opts.doctype ? [f[0], f[1], f[2], f[3]] : [f[1], f[2], f[3]]);
                frm.set_value(opts.field, filters.length ? JSON.stringify(filters) : '');
                dialog.hide();
            }
        });

        try {
            filter_group = new frappe.ui.FilterGroup({
                parent: dialog.get_field('filter_area').$wrapper,
                doctype: opts.doctype,
                on_change: () => {}
            });
            filter_group.add_filters_to_filter_group(current.map(f => f.length === 4 ? f : [opts.doctype].concat(f)));
        } catch (e) {
            frappe.msgprint(__('The filter editor is not available in this Frappe version. Please edit the JSON directly.'));
            return;
        }
        dialog.show();
    });
};

// ============================================================
// Template helper: insert fields, ready-made snippets and
// variables into a Jinja message template with one click.
// ============================================================

frappe.whatsapp.LAYOUT_TYPES = ['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Fold', 'Heading',
    'Image', 'Attach', 'Attach Image', 'Signature', 'Geolocation', 'Password', 'Barcode'];
frappe.whatsapp.NUMERIC_TYPES = ['Currency', 'Float', 'Int', 'Percent'];

/** Jinja expression for a field, formatted by its type. `obj` is "doc", "d", "row"... */
frappe.whatsapp.field_expr = function(df, obj, meta) {
    let ref = `${obj}.${df.fieldname}`;
    if (df.fieldtype === 'Currency') {
        let cur = meta && meta.fields.some(f => f.fieldname === 'currency') ? `, ${obj}.currency` : '';
        return `{{ format_currency(${ref}${cur}) }}`;
    }
    if (df.fieldtype === 'Date') return `{{ format_date(${ref}) }}`;
    if (df.fieldtype === 'Datetime') return `{{ format_datetime(${ref}) }}`;
    if (df.fieldtype === 'Check') return `{{ "✅" if ${ref} else "❌" }}`;
    return `{{ ${ref} }}`;
};

/** Best "title" field: title_field, then common name fields, then name. */
frappe.whatsapp.guess_title_field = function(meta) {
    let has = f => meta.fields.some(x => x.fieldname === f);
    if (meta.title_field && meta.title_field !== 'name' && has(meta.title_field)) return meta.title_field;
    return ['customer_name', 'supplier_name', 'employee_name', 'party_name', 'applicant_name',
        'full_name', 'title', 'subject', 'item_name'].find(has) || null;
};

/** Best amount field: outstanding first (what reminders care about), then totals, then any currency. */
frappe.whatsapp.guess_amount_field = function(meta) {
    let has = f => meta.fields.some(x => x.fieldname === f);
    return ['outstanding_amount', 'total_amount', 'grand_total', 'rounded_total', 'amount', 'loan_amount', 'total']
        .find(has) || (meta.fields.find(f => f.fieldtype === 'Currency') || {}).fieldname || null;
};

/**
 * Render the helper under a template field.
 * opts: {
 *   field: 'message_template', doctype,
 *   mode: 'doc' (one document -> doc.x) | 'list' (Document List -> docs loop)
 *         | 'report' (saved report: no doctype, only variables/snippets/tags),
 *   variables: [[code, description], ...],
 *   snippets: function(ctx) -> [{label, text, hint}], ctx = {meta, title, amount, obj}
 * }
 */
frappe.whatsapp.template_helper = function(frm, opts) {
    let fld = frm.get_field(opts.field);
    if (!fld) return;
    fld.$wrapper.find('.wa-template-helper').remove();
    if (!opts.doctype && opts.mode !== 'report') return;

    let esc = frappe.utils.escape_html;

    let insert = function(text) {
        let editor = fld.editor;
        if (editor && typeof editor.insert === 'function') {
            editor.focus();
            editor.insert(text);
        } else {
            let current = frm.doc[opts.field] || '';
            frm.set_value(opts.field, current + (current && !current.endsWith('\n') ? '\n' : '') + text);
        }
        frappe.show_alert({ message: __('Inserted into the template'), indicator: 'green' }, 2);
    };

    let render = function(meta) {
        let obj = opts.mode === 'list' ? 'd' : 'doc';
        let fields = meta ? meta.fields.filter(df => !frappe.whatsapp.LAYOUT_TYPES.includes(df.fieldtype) && df.fieldtype !== 'Table'
            && df.fieldtype !== 'Table MultiSelect' && !df.hidden) : [];
        let ctx = {
            meta: meta,
            obj: obj,
            title: meta ? frappe.whatsapp.guess_title_field(meta) : null,
            amount: meta ? frappe.whatsapp.guess_amount_field(meta) : null,
            amount_df: null,
        };
        ctx.amount_df = ctx.amount ? meta.fields.find(f => f.fieldname === ctx.amount) : null;

        // Field picker (no document fields in report mode, only tags)
        let $select = $(`<select class="form-control input-xs" style="max-width:320px;display:inline-block;"></select>`);
        $select.append(`<option value="">${esc(meta ? __('➕ Insert field…') : __('🏷️ Tag a person…'))}</option>`);
        let exprs = {};
        let add_option = ($group, key, label, expr) => {
            exprs[key] = expr;
            $group.append($('<option></option>').val(key).text(label));
        };
        if (meta) {
            let $fields = $(`<optgroup label="${esc(opts.mode === 'list' ? __('Field (inside the list loop)') : __('Field'))}"></optgroup>`);
            add_option($fields, 'f:name', `${__('ID')} (name)`, `{{ ${obj}.name }}`);
            fields.forEach(df => add_option($fields, 'f:' + df.fieldname,
                `${__(df.label || df.fieldname)} (${df.fieldtype})`, frappe.whatsapp.field_expr(df, obj, meta)));
            $select.append($fields);
        }

        if (!meta) {
            // report mode: nothing document-specific to add
        } else if (opts.mode === 'list') {
            let numeric = fields.filter(df => frappe.whatsapp.NUMERIC_TYPES.includes(df.fieldtype));
            if (numeric.length) {
                let $totals = $(`<optgroup label="${esc(__('Total of all matching documents'))}"></optgroup>`);
                numeric.forEach(df => add_option($totals, 't:' + df.fieldname, `Σ ${__(df.label || df.fieldname)}`,
                    df.fieldtype === 'Currency' ? `{{ format_currency(total('${df.fieldname}')) }}` : `{{ total('${df.fieldname}') }}`));
                $select.append($totals);
            }
        } else {
            // Child tables: loop over rows
            let tables = meta.fields.filter(df => df.fieldtype === 'Table' && df.options);
            if (tables.length) {
                let $tables = $(`<optgroup label="${esc(__('List rows of a table'))}"></optgroup>`);
                tables.forEach(df => {
                    let child = frappe.get_meta(df.options);
                    let child_title = child ? frappe.whatsapp.guess_title_field(child) : null;
                    let qty = child && child.fields.some(f => f.fieldname === 'qty') ? ' x {{ row.qty }}' : '';
                    let line = child_title ? `{{ row.${child_title} }}` : '{{ row.idx }}';
                    add_option($tables, 'r:' + df.fieldname, `🔁 ${__(df.label || df.fieldname)}`,
                        `{% for row in doc.${df.fieldname} %}• ${line}${qty}\n{% endfor %}`);
                });
                $select.append($tables);
            }
        }

        // Tag individual people: {{ tag('supervisor') }}
        let tag_keys = opts.tag_keys ? opts.tag_keys() : [];
        if (tag_keys.length) {
            let $tags = $(`<optgroup label="${esc(__('🏷️ Tag a person'))}"></optgroup>`);
            tag_keys.forEach(t => add_option($tags, 'g:' + t.key, t.label, `{{ tag('${t.key}') }} `));
            $select.append($tags);
        }

        $select.on('change', function() {
            let key = $(this).val();
            if (key && exprs[key]) insert(exprs[key]);
            $(this).val('');
        });

        // Snippets
        let snippets = (opts.snippets ? opts.snippets(ctx) : []).filter(Boolean);
        let roles = tag_keys.filter(t => t.is_role);
        if (roles.length) {
            let lines = roles.slice(0, 3).map((t, i) =>
                `{{ tag('${t.key}') }} ` + [__('acompanhe esta tarefa.'), __('garanta que está tudo a funcionar.'), __('para conhecimento.')][i]);
            snippets.push({ label: __('Different task per person'), hint: __('One line per role; edit the text after each tag'),
                text: lines.join('\n') + '\n' });
        }
        let $snippets = $('<div class="d-flex flex-wrap mt-2" style="gap:6px;"></div>');
        snippets.forEach(s => {
            let $btn = $(`<button type="button" class="btn btn-default btn-xs"></button>`).text(s.label);
            if (s.hint) $btn.attr('title', s.hint);
            $btn.on('click', () => insert(s.text));
            $snippets.append($btn);
        });

        // Variables
        let vars = (opts.variables || []).map(v =>
            `<li><a href="#" class="wa-insert-var" data-code="${esc(v[0])}"><code>${esc(v[0])}</code></a> — ${esc(v[1])}</li>`).join('');

        let $box = $(`
            <div class="wa-template-helper mt-2 p-3 rounded border" style="background:var(--subtle-accent, #f8f9fa);">
                <div class="small text-muted mb-2">${esc(__('Click to insert at the cursor:'))}</div>
                <div class="wa-field-picker"></div>
                <div class="wa-snippets"></div>
                <details class="mt-2">
                    <summary class="small text-muted" style="cursor:pointer;">${esc(__('All variables & formatting'))}</summary>
                    <ul class="small mt-2 mb-1">${vars}</ul>
                    <div class="small text-muted">${esc(__('WhatsApp formatting:'))} <code>*bold*</code> <code>_italic_</code> <code>~strike~</code></div>
                </details>
            </div>`);
        if (Object.keys(exprs).length) $box.find('.wa-field-picker').append($select);
        $box.find('.wa-snippets').append($snippets);
        $box.on('click', '.wa-insert-var', function(e) {
            e.preventDefault();
            insert($(this).data('code'));
        });
        fld.$wrapper.find('.wa-template-helper').remove();
        fld.$wrapper.append($box);
    };

    if (opts.doctype) {
        frappe.model.with_doctype(opts.doctype, () => render(frappe.get_meta(opts.doctype)));
    } else {
        render(null);
    }
};
