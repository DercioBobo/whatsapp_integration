// WhatsApp Notification Rule - Client Script

const WNR_MODULE = 'whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule';

frappe.ui.form.on('WhatsApp Notification Rule', {
    refresh: function (frm) {
        if (!frm.is_new() && frm.doc.document_type) {
            frm.add_custom_button(__('Preview Message'), function () {
                show_preview_dialog(frm);
            }, __('Actions'));

            frm.add_custom_button(__('Test Send'), function () {
                show_test_dialog(frm);
            }, __('Actions'));

            frm.add_custom_button(__('View Logs'), function () {
                frappe.set_route('List', 'WhatsApp Message Log', {
                    notification_rule: frm.doc.name
                });
            }, __('Actions'));

            if (frm.doc.event === 'Recurring') {
                frm.add_custom_button(__('Preview Recurring Run'), function () {
                    show_recurring_preview(frm);
                }, __('Actions'));

                frm.add_custom_button(__('Run Now'), function () {
                    run_recurring_now(frm);
                }, __('Actions'));
            }
        }

        setup_template_help(frm);
        describe_recurring_filters(frm);
        frm._last_group_id = frm.doc.group_id;

        if (frm.doc.document_type) {
            setup_doctype_pickers(frm);
            if (uses_date_field(frm.doc.event)) {
                load_date_fields(frm);
            }
        }

        if (frm.doc.use_child_table && frm.doc.child_table && frm.doc.document_type) {
            setup_child_pickers(frm);
        }
    },

    document_type: function (frm) {
        frm.set_value('phone_field', '');
        frm.set_value('group_mention_fields', '');
        frm.set_value('value_changed', '');
        frm.set_value('child_table', '');
        frm.set_value('child_phone_field', '');
        frm.set_value('child_watch_fields', '');
        frm.set_value('date_field', '');
        frm.set_value('recurring_filters', '');

        destroy_chip_picker(frm, 'phone_field');
        destroy_chip_picker(frm, 'group_mention_fields');
        destroy_chip_picker(frm, 'value_changed');
        destroy_chip_picker(frm, 'child_phone_field');
        destroy_chip_picker(frm, 'child_watch_fields');

        if (frm.doc.document_type) {
            setup_doctype_pickers(frm);
            load_child_table_options(frm);
            if (uses_date_field(frm.doc.event)) {
                load_date_fields(frm);
            }
        }
        setup_template_help(frm);
    },

    date_field: function (frm) {
        setup_template_help(frm);
    },

    event: function (frm) {
        if (uses_date_field(frm.doc.event)) {
            load_date_fields(frm);
        }
        setup_template_help(frm);
        describe_recurring_filters(frm);
        // Refresh value_changed picker visibility when event changes
        if (frm.doc.document_type) {
            destroy_chip_picker(frm, 'value_changed');
            if (frm.doc.event === 'On Change' || frm.doc.event === 'On Update') {
                frappe.call({
                    method: WNR_MODULE + '.get_doctype_watch_fields',
                    args: { doctype: frm.doc.document_type },
                    callback: function (r) {
                        if (r.message) {
                            setup_chip_picker(frm, 'value_changed', r.message, __('Add Watch Field'));
                        }
                    }
                });
            }
        }
    },

    recipient_type: function (frm) {
        let needs_group = ['WhatsApp Group', 'Document + Group'].includes(frm.doc.recipient_type);
        if (!needs_group) {
            frm.set_value('group_id', '');
            frm.set_value('group_name', '');
            clear_group_mentions(frm);
        }
        setup_template_help(frm);
    },

    group_id: function (frm) {
        // Members picked for a previous group don't belong to the new one
        if (frm.doc.group_mentions && frm._last_group_id && frm._last_group_id !== frm.doc.group_id) {
            frm.set_value('group_mentions', '');
            frappe.show_alert({ message: __('Group changed: tagged members were cleared'), indicator: 'orange' }, 4);
        }
        // Group removed: nothing left to tag
        if (!frm.doc.group_id) {
            clear_group_mentions(frm);
        }
        frm._last_group_id = frm.doc.group_id;
        setup_template_help(frm);
    },

    group_mentions: function (frm) {
        setup_template_help(frm);
    },

    group_mention_fields: function (frm) {
        setup_template_help(frm);
    },

    select_mentions_button: function (frm) {
        show_mention_selection_dialog(frm);
    },

    use_child_table: function (frm) {
        destroy_chip_picker(frm, 'child_phone_field');
        destroy_chip_picker(frm, 'child_watch_fields');
        if (frm.doc.use_child_table && frm.doc.child_table) {
            setup_child_pickers(frm);
        }
    },

    child_table: function (frm) {
        frm.set_value('child_phone_field', '');
        frm.set_value('child_watch_fields', '');
        destroy_chip_picker(frm, 'child_phone_field');
        destroy_chip_picker(frm, 'child_watch_fields');
        if (frm.doc.child_table) {
            setup_child_pickers(frm);
        }
    },

    select_group_button: function (frm) {
        show_group_selection_dialog(frm);
    },

    edit_recurring_filters_button: function (frm) {
        show_recurring_filters_dialog(frm);
    },

    recurring_filters: function (frm) {
        describe_recurring_filters(frm);
    }
});

function describe_recurring_filters(frm) {
    if (frm.doc.event !== 'Recurring') return;
    frappe.whatsapp.describe_filters(frm, { doctype: frm.doc.document_type, field: 'recurring_filters' });
}

function uses_date_field(event) {
    return ['Days Before', 'Days After', 'On Same Day', 'Recurring'].includes(event);
}

// ─── Chip Picker ──────────────────────────────────────────────────────────────

function setup_chip_picker(frm, fieldname, options, placeholder) {
    let field = frm.get_field(fieldname);
    if (!field) return;

    // Hide native input
    field.$input_wrapper.hide();

    // Remove any previous instance
    field.$wrapper.find('.chip-picker-wrapper').remove();

    let current_values = (frm.doc[fieldname] || '').split(',').map(v => v.trim()).filter(Boolean);

    let $wrapper = $('<div class="chip-picker-wrapper" style="margin-top:4px;"></div>');
    let $select = $(`<select class="form-control form-control-sm"><option value="">-- ${frappe.utils.escape_html(placeholder || __('Add Field'))} --</option></select>`);
    let $chips = $('<div class="chip-container" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;min-height:28px;"></div>');

    function get_label(val) {
        let opt = options.find(o => o.value === val);
        return opt ? opt.label : val;
    }

    function sync_value() {
        frm.set_value(fieldname, current_values.join(','));
    }

    function rebuild_dropdown() {
        $select.find('option:not(:first)').remove();
        options.forEach(opt => {
            if (!current_values.includes(opt.value)) {
                $select.append($('<option></option>').val(opt.value).text(opt.label));
            }
        });
    }

    function render_chips() {
        $chips.empty();
        current_values.forEach(val => {
            let $chip = $(`
                <span style="display:inline-flex;align-items:center;background:#e8f4fd;border:1px solid #b3d9f5;border-radius:12px;padding:2px 8px;font-size:0.82em;line-height:1.6;">
                    ${frappe.utils.escape_html(get_label(val))}
                    <a href="#" data-val="${frappe.utils.escape_html(val)}" style="margin-left:5px;color:#666;text-decoration:none;font-weight:bold;">×</a>
                </span>
            `);
            $chip.find('a').on('click', function (e) {
                e.preventDefault();
                let v = $(this).data('val');
                current_values = current_values.filter(x => x !== v);
                sync_value();
                rebuild_dropdown();
                render_chips();
            });
            $chips.append($chip);
        });
    }

    $select.on('change', function () {
        let val = $(this).val();
        if (val && !current_values.includes(val)) {
            current_values.push(val);
            sync_value();
            rebuild_dropdown();
            render_chips();
        }
        $(this).val('');
    });

    rebuild_dropdown();
    render_chips();
    $wrapper.append($select).append($chips);
    field.$wrapper.append($wrapper);
}

function destroy_chip_picker(frm, fieldname) {
    let field = frm.get_field(fieldname);
    if (!field) return;
    field.$wrapper.find('.chip-picker-wrapper').remove();
    field.$input_wrapper.show();
}

// ─── Field Loaders ────────────────────────────────────────────────────────────

function setup_doctype_pickers(frm) {
    if (!frm.doc.document_type) return;

    frappe.call({
        method: WNR_MODULE + '.get_doctype_fields',
        args: { doctype: frm.doc.document_type },
        callback: function (r) {
            if (r.message) {
                setup_chip_picker(frm, 'phone_field', r.message, __('Add Phone Field'));
                setup_chip_picker(frm, 'group_mention_fields', r.message, __('Add Phone Field to Tag'));
            }
        }
    });

    if (frm.doc.event === 'On Change' || frm.doc.event === 'On Update') {
        frappe.call({
            method: WNR_MODULE + '.get_doctype_watch_fields',
            args: { doctype: frm.doc.document_type },
            callback: function (r) {
                if (r.message) {
                    setup_chip_picker(frm, 'value_changed', r.message, __('Add Watch Field'));
                }
            }
        });
    }
}

function setup_child_pickers(frm) {
    if (!frm.doc.document_type || !frm.doc.child_table) return;

    frappe.call({
        method: WNR_MODULE + '.get_child_table_fields',
        args: { doctype: frm.doc.document_type, child_table_field: frm.doc.child_table },
        callback: function (r) {
            if (r.message) {
                setup_chip_picker(frm, 'child_phone_field', r.message, __('Add Phone Field'));
            }
        }
    });

    frappe.call({
        method: WNR_MODULE + '.get_child_table_fields',
        args: { doctype: frm.doc.document_type, child_table_field: frm.doc.child_table, all_fields: 1 },
        callback: function (r) {
            if (r.message) {
                setup_chip_picker(frm, 'child_watch_fields', r.message, __('Add Watch Field'));
            }
        }
    });
}

function load_child_table_options(frm) {
    if (!frm.doc.document_type) return;
    frappe.call({
        method: WNR_MODULE + '.get_child_tables',
        args: { doctype: frm.doc.document_type },
        callback: function (r) {
            if (r.message) {
                let opts = [''].concat(r.message.map(t => t.fieldname));
                frm.set_df_property('child_table', 'options', opts.join('\n'));
                frm.refresh_field('child_table');
            }
        }
    });
}

function load_date_fields(frm) {
    if (!frm.doc.document_type) return;
    frappe.call({
        method: WNR_MODULE + '.get_doctype_date_fields',
        args: { doctype: frm.doc.document_type },
        callback: function (r) {
            if (r.message) {
                let opts = [''].concat(r.message.map(f => f.value));
                frm.set_df_property('date_field', 'options', opts.join('\n'));
                frm.refresh_field('date_field');
            }
        }
    });
}

// ─── Template Help ────────────────────────────────────────────────────────────

function setup_template_help(frm) {
    // Old static panel (pre template-helper versions)
    frm.fields_dict.message_template.$wrapper.siblings('.template-help').remove();

    let recurring = frm.doc.event === 'Recurring';
    let has_group = ['WhatsApp Group', 'Document + Group'].includes(frm.doc.recipient_type);

    let variables = [
        ['{{ doc.name }}', __('Document ID')],
        ['{{ doc.fieldname }}', __('Any document field')],
        ['{{ row.fieldname }}', __('Child row field (when using child table)')],
        ['{{ changed_fields }}', __('List of changed field names')],
        ['{{ changed_values.fieldname }}', __('New value of changed field')],
        ['{{ previous_values.fieldname }}', __('Old value of changed field')],
        ['{{ format_date(doc.posting_date) }}', __('Formatted date')],
        ['{{ format_currency(doc.grand_total, doc.currency) }}', __('Formatted amount')],
        ['{{ get_url() }}/app/' + frappe.router.slug(frm.doc.document_type || '') + '/{{ doc.name }}', __('Link to the document')],
        ['{{ mentions }}', __('Tags for group members. Appended at the end if not used.')],
        ["{{ tag('supervisor') }}", __('Tag one person by role (set roles in Select Members to Tag)')],
    ];
    if (recurring) {
        variables.push(
            ['{{ reminder_number }}', __('1 on the first reminder, 2 on the second...')],
            ['{{ days_overdue }}', __('Days since the Date Field (negative = not yet due)')],
            ['{{ days_until }}', __('Days until the Date Field')],
            ['{{ last_sent }}', __('When the previous reminder was sent (empty on the first)')]
        );
    }

    frappe.whatsapp.template_helper(frm, {
        field: 'message_template',
        doctype: frm.doc.document_type,
        mode: 'doc',
        tag_keys: has_group ? () => frappe.whatsapp.tag_keys(frm, 'group_mentions', 'group_mention_fields') : null,
        variables: variables,
        snippets: function (ctx) {
            let title = ctx.title ? `{{ doc.${ctx.title} }}` : '{{ doc.name }}';
            let amount = ctx.amount_df ? frappe.whatsapp.field_expr(ctx.amount_df, 'doc', ctx.meta) : null;
            let date = frm.doc.date_field ? `{{ format_date(doc.${frm.doc.date_field}) }}` : null;
            return [
                { label: __('Greeting'), text: `Olá ${title},\n` },
                { label: __('Document + amount'), text: `*{{ doc.name }}*${amount ? ' — ' + amount : ''}\n` },
                date && { label: __('Due date'), text: `Vencimento: ${date}\n` },
                recurring && { label: __('Reminder that gets firmer'),
                    hint: __('Friendly first, then numbered warnings'),
                    text: `{% if reminder_number == 1 %}Lembrete amigável:{% else %}*{{ reminder_number }}º aviso:*{% endif %} ` +
                          `*{{ doc.name }}*${amount ? ' de ' + amount : ''}` +
                          `${frm.doc.date_field ? ' venceu há {{ days_overdue }} dias.' : '.'}\n` },
                recurring && frm.doc.date_field && { label: __('Overdue / due soon'),
                    text: `{% if days_overdue > 0 %}Em atraso há {{ days_overdue }} dias{% elif days_overdue == 0 %}Vence hoje{% else %}Vence em {{ days_until }} dias{% endif %}\n` },
                { label: __('Only if…'), hint: __('Show a line only when a condition is true'),
                    text: `{% if doc.status == "Overdue" %}⚠️ Em atraso{% endif %}\n` },
                { label: __('Link'), text: `🔗 {{ get_url() }}/app/${frappe.router.slug(frm.doc.document_type)}/{{ doc.name }}\n` },
                has_group && { label: __('Group tags'), text: '{{ mentions }}' },
            ];
        }
    });
}

// ─── Group Picker ─────────────────────────────────────────────────────────────

function show_group_selection_dialog(frm) {
    frappe.whatsapp.pick_group(frm, { id_field: 'group_id', name_field: 'group_name' });
}

// ─── Group Member Mentions ────────────────────────────────────────────────────

function clear_group_mentions(frm) {
    if (frm.doc.mention_everyone) frm.set_value('mention_everyone', 0);
    if (frm.doc.group_mentions) frm.set_value('group_mentions', '');
    if (frm.doc.group_mention_fields) frm.set_value('group_mention_fields', '');
}

function show_mention_selection_dialog(frm) {
    frappe.whatsapp.pick_group_members(frm, { group_field: 'group_id', group_name_field: 'group_name', mentions_field: 'group_mentions' });
}

// ─── Preview ──────────────────────────────────────────────────────────────────

function show_preview_dialog(frm) {
    if (frm.is_dirty()) {
        frappe.msgprint(__('Please save the document before previewing.'));
        return;
    }

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: frm.doc.document_type,
            limit_page_length: 10,
            order_by: 'creation desc'
        },
        callback: function (r) {
            if (!r.message || r.message.length === 0) {
                frappe.msgprint(__('No documents found for preview'));
                return;
            }

            let options = r.message.map(d => d.name);

            let dialog = new frappe.ui.Dialog({
                title: __('Preview Message'),
                fields: [
                    { fieldname: 'docname', fieldtype: 'Select', label: __('Select Document'), options: options, default: options[0], reqd: 1 },
                    { fieldname: 'preview_section', fieldtype: 'Section Break' },
                    { fieldname: 'preview_html', fieldtype: 'HTML' }
                ],
                primary_action_label: __('Refresh'),
                primary_action: function (values) {
                    render_preview(frm, values.docname, dialog);
                }
            });

            dialog.show();
            render_preview(frm, options[0], dialog);
        }
    });
}

function render_preview(frm, docname, dialog) {
    frappe.call({
        method: WNR_MODULE + '.preview_message',
        args: { rule_name: frm.doc.name, docname: docname },
        callback: function (r) {
            if (!r.message) return;

            let html;
            let bubble = msg => render_message_with_tags(msg, r.message.mention_names || {});
            let everyone = r.message.mention_everyone
                ? `<div class="text-muted small mb-1"><span class="indicator-pill blue">${__('Tags everyone')}</span></div>` : '';
            if (r.message.row_previews) {
                if (r.message.row_previews.length === 0) {
                    html = `<p class="text-muted">${__('No matching rows found')}</p>`;
                } else {
                    html = r.message.row_previews.map(rp => `
                        <div class="mb-3 p-2 border rounded">
                            <div class="text-muted small mb-1">
                                ${__('Row')}: ${frappe.utils.escape_html(rp.row || 'N/A')} &nbsp;|&nbsp;
                                ${rp.type === 'group' ? __('Group') : __('Phone')}: ${frappe.utils.escape_html(rp.recipient)}
                            </div>
                            ${rp.type === 'group' ? everyone : ''}
                            <div style="background:#DCF8C6;padding:8px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;">${bubble(rp.message || '')}</div>
                        </div>
                    `).join('');
                }
            } else {
                html = `
                    <div class="mb-3">
                        <label class="text-muted">${__('Recipients')}:</label>
                        <div>${frappe.utils.escape_html((r.message.recipients || []).join(', ') || __('No recipients found'))}</div>
                    </div>
                    ${(r.message.mention_everyone || (r.message.mentions || []).length) ? `
                    <div class="mb-3">
                        <label class="text-muted">${__('Tagged in Group')}:</label>
                        <div>${r.message.mention_everyone ? `<span class="indicator-pill blue">${__('Everyone')}</span> ` : ''}${(r.message.mentions || []).map(n => {
                            let name = (r.message.mention_names || {})[n];
                            return frappe.utils.escape_html(name ? `${name} (+${n})` : `+${n}`);
                        }).join(', ')}</div>
                    </div>` : ''}
                    <div>
                        <label class="text-muted">${__('Message')}:</label>
                        <div style="background:#DCF8C6;padding:12px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;margin-top:4px;">${r.message.message ? bubble(r.message.message) : frappe.utils.escape_html(__('Empty message'))}</div>
                    </div>
                `;
            }

            dialog.fields_dict.preview_html.$wrapper.html(html);
        }
    });
}

// Escape the message and render '@<number>' tags the way WhatsApp shows them:
// highlighted, with the member's name when known (number kept in the tooltip).
function render_message_with_tags(message, names) {
    return frappe.whatsapp.render_tags(message, names);
}

// ─── Recurring ────────────────────────────────────────────────────────────────

const WNR_RECURRING = 'whatsapp_notifications.whatsapp_notifications.recurring';

function show_recurring_filters_dialog(frm) {
    frappe.whatsapp.edit_filters(frm, {
        doctype: frm.doc.document_type,
        field: 'recurring_filters',
        title: __('Which {0} documents get a reminder?', [__(frm.doc.document_type || '')])
    });
}

function show_recurring_preview(frm) {
    if (frm.is_dirty()) {
        frappe.msgprint(__('Please save the rule before previewing.'));
        return;
    }

    frappe.call({
        method: WNR_RECURRING + '.preview_recurring_run',
        args: { rule_name: frm.doc.name, limit: 10 },
        freeze: true,
        freeze_message: __('Working out the next run...'),
        callback: function (r) {
            if (!r.message) return;
            let p = r.message;
            let esc = frappe.utils.escape_html;
            let fmt_dt = v => v ? frappe.datetime.str_to_user(v) : '—';

            let schedule = `
                <div class="row mb-3">
                    <div class="col-sm-3"><div class="text-muted small">${__('Schedule')}</div>
                        <div>${esc(__(p.frequency))} ${__('at')} ${esc(p.send_time)}${p.uses_global_time ? ` <span class="text-muted small">(${__('global')})</span>` : ''}</div></div>
                    <div class="col-sm-3"><div class="text-muted small">${__('Next run')}</div><div>${fmt_dt(p.next_run)}</div></div>
                    <div class="col-sm-3"><div class="text-muted small">${__('Last run')}</div><div>${fmt_dt(p.last_run)}</div></div>
                    <div class="col-sm-3"><div class="text-muted small">${__('Documents')}</div>
                        <div><b>${p.to_send_count}</b> ${__('to send')} · ${p.skipped_count} ${__('skipped')} · ${p.matched} ${__('matched')}</div></div>
                </div>`;

            let items = p.items.length ? p.items.map(it => `
                <div class="mb-3 p-2 border rounded">
                    <div class="small mb-1 d-flex flex-wrap" style="gap:12px;">
                        <a href="/app/${frappe.router.slug(frm.doc.document_type)}/${encodeURIComponent(it.docname)}" target="_blank"><b>${esc(it.docname)}</b></a>
                        <span class="indicator-pill ${it.reminder_number > 1 ? 'orange' : 'blue'}">${__('Reminder #{0}', [it.reminder_number])}</span>
                        ${it.days_overdue !== null && it.days_overdue !== undefined ? `<span class="text-muted">${it.days_overdue >= 0 ? __('{0} days overdue', [it.days_overdue]) : __('due in {0} days', [-it.days_overdue])}</span>` : ''}
                        ${it.last_sent ? `<span class="text-muted">${__('last sent')} ${fmt_dt(it.last_sent)}</span>` : ''}
                    </div>
                    <div class="text-muted small mb-1">${__('To')}: ${esc(it.recipients.join(', ') || __('No recipients found'))}</div>
                    <div style="background:#DCF8C6;padding:8px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;">${render_message_with_tags(it.message || '', p.mention_names || {})}</div>
                </div>`).join('')
                : `<p class="text-muted">${__('Nothing to send on the next run.')}</p>`;

            let more = p.to_send_count > p.items.length
                ? `<p class="text-muted small">${__('…and {0} more', [p.to_send_count - p.items.length])}</p>` : '';

            let skipped = p.skipped.length ? `
                <details class="mt-2"><summary class="text-muted small">${__('Skipped documents')} (${p.skipped_count})</summary>
                    <table class="table table-sm small mt-2"><tbody>
                        ${p.skipped.map(s => `<tr><td>${esc(s.docname)}</td><td class="text-muted">${esc(s.reason)}</td></tr>`).join('')}
                    </tbody></table>
                </details>` : '';

            let dialog = new frappe.ui.Dialog({
                title: __('Recurring Run Preview'),
                size: 'large',
                fields: [{ fieldtype: 'HTML', fieldname: 'preview_html' }],
                primary_action_label: __('Run Now'),
                primary_action: function () {
                    dialog.hide();
                    run_recurring_now(frm, p.to_send_count);
                }
            });
            dialog.fields_dict.preview_html.$wrapper.html(schedule + items + more + skipped);
            if (!p.to_send_count) dialog.get_primary_btn().prop('disabled', true);
            dialog.show();
        }
    });
}

function run_recurring_now(frm, known_count) {
    let confirm_and_run = function (count) {
        if (!count) {
            frappe.msgprint(__('No documents to remind right now.'));
            return;
        }
        frappe.confirm(
            __('Send {0} reminder(s) now? Documents already reminded today are skipped.', [count]),
            function () {
                frappe.call({
                    method: WNR_RECURRING + '.run_recurring_rule_now',
                    args: { rule_name: frm.doc.name },
                    callback: function (r) {
                        if (r.message && r.message.queued) {
                            frappe.show_alert({ message: __('Reminders queued. Check View Logs for progress.'), indicator: 'green' }, 5);
                        }
                    }
                });
            }
        );
    };

    if (known_count !== undefined) {
        confirm_and_run(known_count);
        return;
    }
    if (frm.is_dirty()) {
        frappe.msgprint(__('Please save the rule first.'));
        return;
    }
    frappe.call({
        method: WNR_RECURRING + '.preview_recurring_run',
        args: { rule_name: frm.doc.name, limit: 1 },
        freeze: true,
        callback: r => r.message && confirm_and_run(r.message.to_send_count)
    });
}

// ─── Test Send ────────────────────────────────────────────────────────────────

function show_test_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Test WhatsApp Notification'),
        fields: [
            { fieldname: 'test_phone', fieldtype: 'Data', label: __('Test Phone Number'), reqd: 1 },
            { fieldname: 'test_docname', fieldtype: 'Dynamic Link', label: __('Test Document'), options: 'test_doctype', reqd: 1 },
            { fieldname: 'test_doctype', fieldtype: 'Data', hidden: 1, default: frm.doc.document_type }
        ],
        primary_action_label: __('Send Test'),
        primary_action: function (values) {
            frappe.call({
                method: WNR_MODULE + '.preview_message',
                args: { rule_name: frm.doc.name, docname: values.test_docname },
                callback: function (r) {
                    // Use the untagged text: tags only work in groups, not in a test chat
                    let first_row = r.message && r.message.row_previews && r.message.row_previews[0];
                    let msg = r.message && (
                        r.message.message_plain || r.message.message ||
                        (first_row && (first_row.message_plain || first_row.message))
                    );
                    if (!msg) {
                        frappe.msgprint(__('Could not render message template'));
                        return;
                    }
                    frappe.call({
                        method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp',
                        args: { phone: values.test_phone, message: msg, doctype: frm.doc.document_type, docname: values.test_docname },
                        callback: function (send_r) {
                            if (send_r.message && send_r.message.success) {
                                dialog.hide();
                                frappe.show_alert({ message: __('Test message sent successfully!'), indicator: 'green' }, 5);
                            } else {
                                frappe.msgprint({ title: __('Send Failed'), indicator: 'red', message: (send_r.message && send_r.message.error) || __('Unknown error') });
                            }
                        }
                    });
                }
            });
        }
    });

    dialog.show();
}
