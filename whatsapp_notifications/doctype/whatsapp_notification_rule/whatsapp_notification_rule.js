// WhatsApp Notification Rule - Client Script
// Enhanced form with field suggestions, template preview, and testing

frappe.ui.form.on('WhatsApp Notification Rule', {
    refresh: function(frm) {
        // Add preview button
        if (!frm.is_new() && frm.doc.document_type) {
            frm.add_custom_button(__('Preview Message'), function() {
                show_preview_dialog(frm);
            }, __('Actions'));
            
            frm.add_custom_button(__('Test Send'), function() {
                show_test_dialog(frm);
            }, __('Actions'));
            
            frm.add_custom_button(__('View Logs'), function() {
                frappe.set_route('List', 'WhatsApp Message Log', {
                    notification_rule: frm.doc.name
                });
            }, __('Actions'));
        }
        
        // Template help
        setup_template_help(frm);
    },
    
    document_type: function(frm) {
        // Clear field suggestions when doctype changes
        frm.set_value('phone_field', '');
        frm.set_value('value_changed', '');
        
        if (frm.doc.document_type) {
            // Load field options
            load_field_options(frm);
        }
    },
    
    event: function(frm) {
        // Show/hide value_changed field
        frm.toggle_reqd('value_changed', frm.doc.event === 'On Change');
    },
    
    recipient_type: function(frm) {
        // Show/hide phone_field based on type
        frm.toggle_reqd('phone_field', frm.doc.recipient_type !== 'Fixed Number');
        frm.toggle_reqd('fixed_recipients', frm.doc.recipient_type !== 'Field Value');
    }
});

function load_field_options(frm) {
    if (!frm.doc.document_type) return;
    
    frappe.call({
        method: 'whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule.get_doctype_fields',
        args: { doctype: frm.doc.document_type },
        callback: function(r) {
            if (r.message) {
                // Store for autocomplete
                frm.__field_options = r.message;
                
                // Update phone_field description with examples
                let phone_fields = r.message.filter(f => 
                    f.label.toLowerCase().includes('phone') || 
                    f.label.toLowerCase().includes('mobile') ||
                    f.value.includes('phone') ||
                    f.value.includes('mobile')
                );
                
                if (phone_fields.length > 0) {
                    let suggestions = phone_fields.map(f => f.value).slice(0, 3).join(', ');
                    frm.set_df_property('phone_field', 'description', 
                        __('Suggested fields: ') + suggestions
                    );
                }
            }
        }
    });
}

function setup_template_help(frm) {
    if (!frm.doc.document_type) return;
    
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
        callback: function(r) {
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
                primary_action: function(values) {
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
        method: 'whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule.preview_message',
        args: {
            rule_name: frm.doc.name,
            docname: docname
        },
        callback: function(r) {
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
                fieldtype: 'Link',
                label: __('Test Document'),
                options: frm.doc.document_type,
                reqd: 1,
                get_query: function () {
                    return {
                        doctype: frm.doc.document_type
                    };
                }
            },

            {
                fieldname: 'test_doctype',
                fieldtype: 'Data',
                hidden: 1,
                default: frm.doc.document_type
            }
        ],
        primary_action_label: __('Send Test'),
        primary_action: function(values) {
            // First preview the message
            frappe.call({
                method: 'whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule.preview_message',
                args: {
                    rule_name: frm.doc.name,
                    docname: values.test_docname
                },
                callback: function(r) {
                    if (r.message && r.message.message) {
                        // Now send the test
                        frappe.call({
                            method: 'whatsapp_notifications.api.send_whatsapp',
                            args: {
                                phone: values.test_phone,
                                message: r.message.message,
                                doctype: frm.doc.document_type,
                                docname: values.test_docname
                            },
                            callback: function(send_r) {
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
