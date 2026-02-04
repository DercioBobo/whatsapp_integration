// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Evolution API Settings', {
    refresh: function(frm) {
        // Generate and display webhook URL
        var site_url = window.location.origin;
        var webhook_url = site_url + '/api/method/whatsapp_notifications.whatsapp_notifications.webhook.receive_message';
        frm.set_value('webhook_url', webhook_url);

        // Add custom buttons for webhook management
        if (frm.doc.api_url && frm.doc.instance_name) {
            frm.add_custom_button(__('Check Webhook Status'), function() {
                frm.call({
                    doc: frm.doc,
                    method: 'get_webhook_status',
                    freeze: true,
                    freeze_message: __('Checking webhook status...'),
                    callback: function(r) {
                        if (r.message) {
                            if (r.message.success) {
                                var status = r.message.enabled ? 'Enabled' : 'Disabled';
                                var msg = __('Webhook Status: {0}', [status]);
                                msg += '<br><br><strong>' + __('URL:') + '</strong> ' + (r.message.url || 'Not set');
                                msg += '<br><strong>' + __('Events:') + '</strong> ' + (r.message.events || []).join(', ');

                                frappe.msgprint({
                                    title: __('Webhook Configuration'),
                                    indicator: r.message.enabled ? 'green' : 'orange',
                                    message: msg
                                });
                            } else {
                                frappe.msgprint({
                                    title: __('Webhook Status'),
                                    indicator: 'orange',
                                    message: r.message.message || __('Could not retrieve webhook status')
                                });
                            }
                        }
                    }
                });
            }, __('Webhook'));
        }
    },

    configure_webhook: function(frm) {
        // Configure webhook in Evolution API
        if (!frm.doc.api_url || !frm.doc.instance_name) {
            frappe.msgprint({
                title: __('Configuration Required'),
                indicator: 'orange',
                message: __('Please configure API URL and Instance Name first')
            });
            return;
        }

        frappe.confirm(
            __('This will configure the webhook in Evolution API to send incoming messages to this Frappe site. Continue?'),
            function() {
                frm.call({
                    doc: frm.doc,
                    method: 'configure_webhook',
                    freeze: true,
                    freeze_message: __('Configuring webhook in Evolution API...'),
                    callback: function(r) {
                        if (r.message) {
                            if (r.message.success) {
                                frappe.show_alert({
                                    message: __('Webhook configured successfully!'),
                                    indicator: 'green'
                                }, 5);
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __('Configuration Failed'),
                                    indicator: 'red',
                                    message: r.message.message || __('Failed to configure webhook')
                                });
                            }
                        }
                    }
                });
            }
        );
    },

    copy_webhook_url: function(frm) {
        // Copy webhook URL to clipboard
        var webhook_url = frm.doc.webhook_url;

        if (webhook_url) {
            frappe.utils.copy_to_clipboard(webhook_url);
            frappe.show_alert({
                message: __('Webhook URL copied to clipboard'),
                indicator: 'green'
            });
        } else {
            frappe.show_alert({
                message: __('No webhook URL to copy'),
                indicator: 'red'
            });
        }
    },

    clear_message_logs: function(frm) {
        frappe.confirm(
            __('This will permanently delete ALL WhatsApp Message Logs. This action cannot be undone. Are you sure?'),
            function() {
                frappe.call({
                    method: 'whatsapp_notifications.whatsapp_notifications.api.clear_all_message_logs',
                    freeze: true,
                    freeze_message: __('Clearing message logs...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Deleted {0} message logs', [r.message.count]),
                                indicator: 'green'
                            }, 5);
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message ? r.message.error : __('Failed to clear logs')
                            });
                        }
                    }
                });
            }
        );
    },

    clear_approval_requests: function(frm) {
        frappe.confirm(
            __('This will permanently delete ALL WhatsApp Approval Requests. This action cannot be undone. Are you sure?'),
            function() {
                frappe.call({
                    method: 'whatsapp_notifications.whatsapp_notifications.api.clear_all_approval_requests',
                    freeze: true,
                    freeze_message: __('Clearing approval requests...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Deleted {0} approval requests', [r.message.count]),
                                indicator: 'green'
                            }, 5);
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message ? r.message.error : __('Failed to clear requests')
                            });
                        }
                    }
                });
            }
        );
    }
});
