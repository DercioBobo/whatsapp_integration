// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Evolution API Settings', {
    refresh: function(frm) {
        // Generate and display webhook URL
        var site_url = window.location.origin;
        var webhook_url = site_url + '/api/method/whatsapp_notifications.whatsapp_notifications.webhook.receive_message';
        frm.set_value('webhook_url', webhook_url);
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
    }
});
