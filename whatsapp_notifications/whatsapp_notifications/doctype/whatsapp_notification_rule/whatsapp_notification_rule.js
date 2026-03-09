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
        }

        setup_template_help(frm);

        if (frm.doc.document_type) {
            setup_doctype_pickers(frm);
            if (frm.doc.event === 'Days Before' || frm.doc.event === 'Days After') {
                load_date_fields(frm);
            }
        }

        if (frm.doc.use_child_table && frm.doc.child_table && frm.doc.document_type) {
            setup_child_pickers(frm);
        }
    },

    document_type: function (frm) {
        frm.set_value('phone_field', '');
        frm.set_value('value_changed', '');
        frm.set_value('child_table', '');
        frm.set_value('child_phone_field', '');
        frm.set_value('child_watch_fields', '');
        frm.set_value('date_field', '');

        destroy_chip_picker(frm, 'phone_field');
        destroy_chip_picker(frm, 'value_changed');
        destroy_chip_picker(frm, 'child_phone_field');
        destroy_chip_picker(frm, 'child_watch_fields');

        if (frm.doc.document_type) {
            setup_doctype_pickers(frm);
            load_child_table_options(frm);
            if (frm.doc.event === 'Days Before' || frm.doc.event === 'Days After') {
                load_date_fields(frm);
            }
        }
    },

    event: function (frm) {
        if (frm.doc.event === 'Days Before' || frm.doc.event === 'Days After') {
            load_date_fields(frm);
        }
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
        }
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
    }
});

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
    if (!frm.doc.document_type) return;

    frm.fields_dict.message_template.$wrapper.siblings('.template-help').remove();

    let help_html = `
        <div class="template-help mt-3 p-3 bg-light rounded">
            <h6><i class="fa fa-info-circle"></i> ${__('Template Variables')}</h6>
            <p class="text-muted small mb-2">${__('Use Jinja2 syntax:')}</p>
            <ul class="small mb-2">
                <li><code>{{ doc.name }}</code> — ${__('Document ID')}</li>
                <li><code>{{ doc.fieldname }}</code> — ${__('Any document field')}</li>
                <li><code>{{ row.fieldname }}</code> — ${__('Child row field (when using child table)')}</li>
                <li><code>{{ changed_fields }}</code> — ${__('List of changed field names')}</li>
                <li><code>{{ changed_values.fieldname }}</code> — ${__('New value of changed field')}</li>
                <li><code>{{ previous_values.fieldname }}</code> — ${__('Old value of changed field')}</li>
                <li><code>{{ format_date(doc.date_field) }}</code> — ${__('Formatted date')}</li>
                <li><code>{{ format_currency(doc.amount, "USD") }}</code> — ${__('Formatted currency')}</li>
            </ul>
            <p class="text-muted small mb-1">${__('WhatsApp formatting:')}</p>
            <ul class="small mb-0">
                <li><code>*bold*</code> | <code>_italic_</code> | <code>~strikethrough~</code></li>
            </ul>
        </div>
    `;

    frm.fields_dict.message_template.$wrapper.after(help_html);
}

// ─── Group Picker ─────────────────────────────────────────────────────────────

function show_group_selection_dialog(frm) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.fetch_whatsapp_groups',
        freeze: true,
        freeze_message: __('Fetching WhatsApp groups...'),
        callback: function (r) {
            if (r.message && r.message.success) {
                let groups = r.message.groups;

                if (!groups || groups.length === 0) {
                    frappe.msgprint(__('No WhatsApp groups found. Make sure your WhatsApp is connected to groups.'));
                    return;
                }

                let dialog = new frappe.ui.Dialog({
                    title: __('Select WhatsApp Group'),
                    fields: [
                        {
                            fieldname: 'group',
                            fieldtype: 'Select',
                            label: __('Group'),
                            options: groups.map(g => g.id),
                            reqd: 1
                        }
                    ],
                    primary_action_label: __('Select'),
                    primary_action: function (values) {
                        let selected = groups.find(g => g.id === values.group);
                        if (selected) {
                            frm.set_value('group_id', selected.id);
                            frm.set_value('group_name', selected.subject);
                            dialog.hide();
                            frappe.show_alert({ message: __('Group selected: ') + selected.subject, indicator: 'green' }, 3);
                        }
                    }
                });

                // Replace select options with labeled text
                let $select = dialog.fields_dict.group.$input;
                $select.empty();
                groups.forEach(g => {
                    $select.append($('<option></option>').val(g.id).text(`${g.subject} (${g.size} members)`));
                });

                if (frm.doc.group_id) {
                    $select.val(frm.doc.group_id);
                }

                dialog.show();
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: (r.message && r.message.error) || __('Failed to fetch WhatsApp groups')
                });
            }
        }
    });
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
                            <div style="background:#DCF8C6;padding:8px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;">
                                ${frappe.utils.escape_html(rp.message || '')}
                            </div>
                        </div>
                    `).join('');
                }
            } else {
                html = `
                    <div class="mb-3">
                        <label class="text-muted">${__('Recipients')}:</label>
                        <div>${frappe.utils.escape_html((r.message.recipients || []).join(', ') || __('No recipients found'))}</div>
                    </div>
                    <div>
                        <label class="text-muted">${__('Message')}:</label>
                        <div style="background:#DCF8C6;padding:12px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;margin-top:4px;">
                            ${frappe.utils.escape_html(r.message.message || __('Empty message'))}
                        </div>
                    </div>
                `;
            }

            dialog.fields_dict.preview_html.$wrapper.html(html);
        }
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
                    let msg = r.message && (r.message.message || (r.message.row_previews && r.message.row_previews[0] && r.message.row_previews[0].message));
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
