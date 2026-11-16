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
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: (r.message && r.message.error) || __('Failed to fetch WhatsApp groups')
                });
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
                }
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

frappe.whatsapp.parse_number_list = function(value) {
    return (value || '').split(/[\n,;\/]+/).map(v => v.replace(/\D/g, '')).filter(Boolean);
};

/**
 * Pick group members to @mention into a newline-separated field.
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

            // Match saved numbers by suffix so "841234567" and "258841234567" are the same member
            let current = frappe.whatsapp.parse_number_list(frm.doc[opts.mentions_field]);
            let same = (a, b) => a === b || a.endsWith(b) || b.endsWith(a);
            let is_selected = n => current.some(c => same(n, c));

            let options = participants.map(p => {
                let label = p.name ? `${p.name} (+${p.number})` : `+${p.number}`;
                if (p.admin) label += ` — ${__('admin')}`;
                return { label: label, value: p.number, checked: is_selected(p.number) ? 1 : 0 };
            });

            // Numbers saved on the form that are no longer in the group are kept
            let orphans = current.filter(c => !participants.some(p => same(p.number, c)));

            let fields = [
                { fieldname: 'search', fieldtype: 'Data', label: __('Search'), placeholder: __('Filter by name or number') },
                { fieldname: 'members', fieldtype: 'MultiCheck', label: __('Members'), columns: 1, options: options }
            ];
            if (orphans.length) {
                fields.push({
                    fieldname: 'orphans_html', fieldtype: 'HTML',
                    options: `<p class="text-muted small">${__('Kept (not found in group)')}: ${frappe.utils.escape_html(orphans.join(', '))}</p>`
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
                    let selected = dialog.fields_dict.members.get_checked_options();
                    frm.set_value(opts.mentions_field, orphans.concat(selected).join('\n'));
                    dialog.hide();
                    frappe.show_alert({ message: __('{0} member(s) will be tagged', [orphans.length + selected.length]), indicator: 'green' }, 3);
                },
                secondary_action_label: __('Clear All'),
                secondary_action: function() {
                    dialog.fields_dict.members.$wrapper.find('input[type=checkbox]').prop('checked', false);
                }
            });

            dialog.fields_dict.search.$input.on('input', function() {
                let q = ($(this).val() || '').toLowerCase().trim();
                dialog.fields_dict.members.$wrapper.find('.checkbox').each(function() {
                    $(this).toggle(!q || $(this).text().toLowerCase().includes(q));
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
