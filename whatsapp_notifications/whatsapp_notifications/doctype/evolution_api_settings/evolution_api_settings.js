// Evolution API Settings - Client Script
// Handles UI interactions for the settings page

frappe.ui.form.on('Evolution API Settings', {
    refresh: function(frm) {
        // Add Test Connection button
        frm.add_custom_button(__('Test Connection'), function() {
            test_evolution_connection(frm);
        }).addClass('btn-primary');
        
        // Add link to documentation
        frm.set_intro(__('Configure your Evolution API connection for WhatsApp messaging. <a href="https://doc.evolution-api.com/" target="_blank">View Documentation</a>'));
        
        // Show connection status indicator
        update_connection_indicator(frm);
    },
    
    enabled: function(frm) {
        if (frm.doc.enabled && (!frm.doc.api_url || !frm.doc.api_key || !frm.doc.instance_name)) {
            frappe.msgprint({
                title: __('Configuration Required'),
                indicator: 'orange',
                message: __('Please configure API URL, API Key, and Instance Name before enabling.')
            });
        }
    },
    
    api_url: function(frm) {
        // Clean up URL
        if (frm.doc.api_url) {
            let url = frm.doc.api_url.trim();
            // Remove trailing slash
            if (url.endsWith('/')) {
                frm.set_value('api_url', url.slice(0, -1));
            }
        }
    }
});

function test_evolution_connection(frm) {
    if (!frm.doc.api_url || !frm.doc.api_key || !frm.doc.instance_name) {
        frappe.msgprint({
            title: __('Missing Configuration'),
            indicator: 'orange',
            message: __('Please fill in API URL, API Key, and Instance Name before testing.')
        });
        return;
    }
    
    // Save first to ensure latest values are used
    frm.save().then(() => {
        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications..doctype.evolution_api_settings.evolution_api_settings.test_api_connection',
            freeze: true,
            freeze_message: __('Testing connection...'),
            callback: function(r) {
                if (r.message) {
                    if (r.message.success) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: 'green'
                        }, 5);
                    } else {
                        frappe.msgprint({
                            title: __('Connection Failed'),
                            indicator: 'red',
                            message: r.message.message
                        });
                    }
                    frm.reload_doc();
                }
            },
            error: function(err) {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Failed to test connection. Check Error Log for details.')
                });
            }
        });
    });
}

function update_connection_indicator(frm) {
    if (frm.doc.connection_status) {
        let indicator = 'gray';
        if (frm.doc.connection_status.startsWith('Connected')) {
            indicator = 'green';
        } else if (frm.doc.connection_status.startsWith('Error')) {
            indicator = 'red';
        }
        
        frm.dashboard.set_headline_alert(
            `<span class="indicator ${indicator}">${frm.doc.connection_status}</span>`,
            indicator
        );
    }
}
