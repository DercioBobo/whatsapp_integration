frappe.listview_settings['WhatsApp Message Log'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__('Clear All Logs'), function() {
            frappe.confirm(__('Are you sure you want to delete ALL message logs? This cannot be undone.'), function() {
                frappe.call({
                    method: 'whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_message_log.whatsapp_message_log.clear_all_logs',
                    freeze: true,
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(__('All logs cleared'));
                            listview.refresh();
                        }
                    }
                });
            });
        });
    }
};
