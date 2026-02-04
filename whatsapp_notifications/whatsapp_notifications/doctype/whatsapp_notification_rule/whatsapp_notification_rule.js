// WhatsApp Notification Rule - Client Script
// Enhanced form with field suggestions, template preview, and testing

frappe.ui.form.on('WhatsApp Notification Rule', {
    refresh: function (frm) {
        // Add preview button
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

        // Template help
        setup_template_help(frm);

        // Initialize group field visibility
        let needs_group = ['Group', 'Phone and Group'].includes(frm.doc.recipient_type);
        frm.toggle_display('group_id', needs_group);
        frm.toggle_display('group_name', needs_group && frm.doc.group_id);
        frm.toggle_display('select_group_button', needs_group);

        // Setup field selectors on refresh
        if (frm.doc.document_type) {
            load_field_options(frm);
        }
    },

    document_type: function (frm) {
        // Clear field suggestions when doctype changes
        frm.set_value('phone_field', '');
        frm.set_value('value_changed', '');

        if (frm.doc.document_type) {
            // Load field options
            load_field_options(frm);
        }
    },

    event: function (frm) {
        // Show/hide value_changed field
        frm.toggle_reqd('value_changed', frm.doc.event === 'On Change');
    },

    recipient_type: function (frm) {
        // Determine which fields to require based on recipient type
        let needs_phone_field = ['Field Value', 'Both', 'Phone and Group'].includes(frm.doc.recipient_type);
        let needs_fixed = ['Fixed Number', 'Both'].includes(frm.doc.recipient_type);
        let needs_group = ['Group', 'Phone and Group'].includes(frm.doc.recipient_type);

        frm.toggle_reqd('phone_field', needs_phone_field && frm.doc.recipient_type !== 'Phone and Group');
        frm.toggle_reqd('fixed_recipients', needs_fixed);

        // Show/hide group fields
        frm.toggle_display('group_id', needs_group);
        frm.toggle_display('group_name', needs_group && frm.doc.group_id);
        frm.toggle_display('select_group_button', needs_group);

        // Clear group fields if not needed
        if (!needs_group) {
            frm.set_value('group_id', '');
            frm.set_value('group_name', '');
        }
    },

    select_group_button: function (frm) {
        show_group_selection_dialog(frm);
    }
});

function load_field_options(frm) {
    if (!frm.doc.document_type) return;

    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_doctype_fields',
        args: { doctype: frm.doc.document_type },
        callback: function (r) {
            if (r.message && r.message.success) {
                var fields = r.message.fields;

                // Populate Select options for phone_field
                let phone_options = fields.map(f => ({
                    label: `${f.label} (${f.fieldname})`,
                    value: f.fieldname
                }));

                // Add empty option
                phone_options.unshift({ label: '', value: '' });

                set_field_options(frm, 'phone_field', phone_options);

                // Populate Select options for value_changed
                set_field_options(frm, 'value_changed', phone_options);
            }
        }
    });
}

function set_field_options(frm, fieldname, options) {
    let field = frm.get_field(fieldname);
    if (field) {
        field.df.options = options;
        field.refresh();
    }
}

function setup_template_help(frm) {
    if (!frm.doc.document_type) return;

    // Remove any existing help text first to prevent duplication
    frm.fields_dict.message_template.$wrapper.siblings('.template-help').remove();

    // Add help text showing available fields
    let help_html = `
        <div class="template-help mt-3 p-3 bg-light rounded">
            <h6><i class="fa fa-info-circle"></i> ${__('Template Variables')}</h6>
            <p class="text-muted small mb-2">${__('Use Jinja2 syntax to include document data:')}</p>
            <ul class="small mb-2">
                <li><code>{{ doc.name }}</code> - ${__('Document ID')}</li>
                <li><code>{{ doc.fieldname }}</code> - ${__('Any document field')}</li>
                <li><code>{{ format_date(doc.date_field) }}</code> - ${__('Formatted date')}</li>
                <li><code>{{ format_currency(doc.amount, "MZN") }}</code> - ${__('Formatted currency')}</li>
            </ul>
            <p class="text-muted small mb-1">${__('WhatsApp formatting:')}</p>
            <ul class="small mb-0">
                <li><code>*bold*</code> | <code>_italic_</code> | <code>~strikethrough~</code></li>
            </ul>
        </div>
    `;

    // Add after message_template field
    frm.fields_dict.message_template.$wrapper.after(help_html);
}

function show_preview_dialog(frm) {
    // Get a recent document of this type for preview
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
                    {
                        fieldname: 'docname',
                        fieldtype: 'Select',
                        label: __('Select Document'),
                        options: options,
                        default: options[0],
                        reqd: 1
                    },
                    {
                        fieldname: 'preview_section',
                        fieldtype: 'Section Break'
                    },
                    {
                        fieldname: 'preview_html',
                        fieldtype: 'HTML'
                    }
                ],
                primary_action_label: __('Refresh Preview'),
                primary_action: function (values) {
                    render_preview(frm, values.docname, dialog);
                }
            });

            dialog.show();

            // Initial preview
            render_preview(frm, options[0], dialog);
        }
    });
}

function render_preview(frm, docname, dialog) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule.preview_message',
        args: {
            rule_name: frm.doc.name,
            docname: docname
        },
        callback: function (r) {
            if (r.message) {
                let html = `
                    <div class="preview-container">
                        <div class="mb-3">
                            <label class="text-muted">${__('Recipients')}:</label>
                            <div class="font-weight-bold">${r.message.recipients.join(', ') || __('No recipients found')}</div>
                        </div>
                        <div>
                            <label class="text-muted">${__('Message')}:</label>
                            <div class="whatsapp-preview p-3 rounded" style="background: #DCF8C6; white-space: pre-wrap; font-family: system-ui, -apple-system, sans-serif;">
                                ${frappe.utils.escape_html(r.message.message || __('Empty message'))}
                            </div>
                        </div>
                    </div>
                `;
                dialog.fields_dict.preview_html.$wrapper.html(html);
            }
        }
    });
}

function show_test_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Test WhatsApp Notification'),
        fields: [
            {
                fieldname: 'test_phone',
                fieldtype: 'Data',
                label: __('Test Phone Number'),
                reqd: 1,
                description: __('Enter a phone number to receive the test message')
            },
            {
                fieldname: 'test_docname',
                fieldtype: 'Dynamic Link',
                label: __('Test Document'),
                options: 'test_doctype',
                reqd: 1
            },
            {
                fieldname: 'test_doctype',
                fieldtype: 'Data',
                hidden: 1,
                default: frm.doc.document_type
            }
        ],
        primary_action_label: __('Send Test'),
        primary_action: function (values) {
            // First preview the message
            frappe.call({
                method: 'whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule.preview_message',
                args: {
                    rule_name: frm.doc.name,
                    docname: values.test_docname
                },
                callback: function (r) {
                    if (r.message && r.message.message) {
                        // Now send the test
                        frappe.call({
                            method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp',
                            args: {
                                phone: values.test_phone,
                                message: r.message.message,
                                doctype: frm.doc.document_type,
                                docname: values.test_docname
                            },
                            callback: function (send_r) {
                                if (send_r.message && send_r.message.success) {
                                    dialog.hide();
                                    frappe.show_alert({
                                        message: __('Test message sent successfully!'),
                                        indicator: 'green'
                                    }, 5);
                                } else {
                                    frappe.msgprint({
                                        title: __('Send Failed'),
                                        indicator: 'red',
                                        message: send_r.message.error || __('Unknown error')
                                    });
                                }
                            }
                        });
                    } else {
                        frappe.msgprint(__('Could not render message template'));
                    }
                }
            });
        }
    });

    dialog.show();
}

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

                // Build options for the select field
                let options = groups.map(g => ({
                    value: g.id,
                    label: g.subject + ' (' + g.size + ' members)'
                }));

                let dialog = new frappe.ui.Dialog({
                    title: __('Select WhatsApp Group'),
                    fields: [
                        {
                            fieldname: 'group',
                            fieldtype: 'Select',
                            label: __('Group'),
                            options: options.map(o => o.value),
                            reqd: 1
                        },
                        {
                            fieldname: 'group_info',
                            fieldtype: 'HTML',
                            options: '<div class="group-list" style="max-height: 300px; overflow-y: auto;"></div>'
                        }
                    ],
                    primary_action_label: __('Select'),
                    primary_action: function (values) {
                        let selected = groups.find(g => g.id === values.group);
                        if (selected) {
                            frm.set_value('group_id', selected.id);
                            frm.set_value('group_name', selected.subject);
                            frm.refresh_field('group_id');
                            frm.refresh_field('group_name');
                            dialog.hide();
                            frappe.show_alert({
                                message: __('Group selected: ') + selected.subject,
                                indicator: 'green'
                            }, 3);
                        }
                    }
                });

                // Populate the select with formatted options
                let $select = dialog.fields_dict.group.$input;
                $select.empty();
                options.forEach(opt => {
                    $select.append($('<option></option>').val(opt.value).text(opt.label));
                });

                // Pre-select current group if set
                if (frm.doc.group_id) {
                    $select.val(frm.doc.group_id);
                }

                dialog.show();
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: r.message.error || __('Failed to fetch WhatsApp groups')
                });
            }
        }
    });
}
