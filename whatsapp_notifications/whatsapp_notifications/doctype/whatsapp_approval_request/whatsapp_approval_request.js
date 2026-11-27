// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Approval Request', {
    refresh: function(frm) {
        if (frm.doc.status === 'Pending') {
            frm.add_custom_button(__('Copy Approval Link'), function() {
                frappe.call({
                    method: 'whatsapp_notifications.whatsapp_notifications.api.get_approval_request_link',
                    args: { request_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            show_approval_link_dialog(r.message.link);
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                message: r.message ? frappe.utils.escape_html(r.message.error) : __('Unknown error'),
                                indicator: 'red'
                            });
                        }
                    }
                });
            });

            if (frm.doc.is_test) {
                frm.dashboard.set_headline_alert(
                    __('Test request: responding on the approval page will not run any action.'), 'orange'
                );
            }
        }

        if ((frm.doc.status === 'Pending' || frm.doc.status === 'Expired') && !frm.doc.is_test) {
            frm.add_custom_button(__('Process Manually'), function() {
                show_manual_process_dialog(frm);
            });
        }
    }
});

function show_approval_link_dialog(link) {
    let d = new frappe.ui.Dialog({
        title: __('Approval Link'),
        fields: [
            {
                fieldname: 'link',
                fieldtype: 'Data',
                label: __('Link'),
                read_only: 1,
                default: link,
                description: __('Anyone with this link can respond. Send it only to the approver.')
            }
        ],
        primary_action_label: __('Copy'),
        primary_action: function() {
            frappe.utils.copy_to_clipboard(link);
        }
    });
    d.show();
}

function show_manual_process_dialog(frm) {
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'WhatsApp Approval Template',
            name: frm.doc.approval_template
        },
        callback: function(r) {
            if (!r.message) {
                frappe.msgprint(__('Could not load approval template'));
                return;
            }

            let template = r.message;
            let options = (template.response_options || [])
                .slice()
                .sort((a, b) => a.option_number - b.option_number)
                .map(o => o.option_number + ' - ' + o.option_label);

            if (!options.length) {
                frappe.msgprint(__('No response options defined in the template'));
                return;
            }

            frappe.prompt([
                {
                    fieldname: 'option',
                    fieldtype: 'Select',
                    label: __('Response Option'),
                    options: options.join('\n'),
                    reqd: 1,
                    description: __('Select the option the recipient actually chose')
                },
                {
                    fieldname: 'note',
                    fieldtype: 'Small Text',
                    label: __('Note (optional)'),
                    description: __('Why you are processing manually — e.g. "Customer replied via phone call"')
                }
            ], function(values) {
                let option_number = parseInt(values.option.split(' - ')[0]);

                frappe.call({
                    method: 'whatsapp_notifications.whatsapp_notifications.api.process_approval_manually',
                    args: {
                        request_name: frm.doc.name,
                        option_number: option_number,
                        note: values.note || null
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Approval processed: {0}', [r.message.status]),
                                indicator: 'green'
                            }, 5);
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                message: r.message ? frappe.utils.escape_html(r.message.error) : __('Unknown error'),
                                indicator: 'red'
                            });
                        }
                    }
                });
            }, __('Process Manually'), __('Process'));
        }
    });
}
