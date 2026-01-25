// WhatsApp Message Log - Client Script
// Provides retry, cancel, and viewing functionality

frappe.ui.form.on('WhatsApp Message Log', {
    refresh: function(frm) {
        // Set indicator based on status
        set_status_indicator(frm);
        
        // Add action buttons based on status
        if (frm.doc.status === 'Failed') {
            frm.add_custom_button(__('Retry Send'), function() {
                retry_message(frm);
            }).addClass('btn-primary');
        }
        
        if (frm.doc.status === 'Pending' || frm.doc.status === 'Queued') {
            frm.add_custom_button(__('Cancel'), function() {
                cancel_message(frm);
            }).addClass('btn-danger');
        }
        
        // Add link to reference document
        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__('View Document'), function() {
                frappe.set_route('Form', frm.doc.reference_doctype, frm.doc.reference_name);
            });
        }
        
        // Format message preview
        format_message_preview(frm);
    }
});

function set_status_indicator(frm) {
    let indicator_map = {
        'Pending': 'orange',
        'Queued': 'blue',
        'Sending': 'blue',
        'Sent': 'green',
        'Delivered': 'green',
        'Read': 'green',
        'Failed': 'red',
        'Cancelled': 'gray'
    };
    
    let indicator = indicator_map[frm.doc.status] || 'gray';
    frm.page.set_indicator(__(frm.doc.status), indicator);
}

function retry_message(frm) {
    frappe.confirm(
        __('Are you sure you want to retry sending this message?'),
        function() {
            frm.call('retry_send').then(r => {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: r.message.message,
                        indicator: 'green'
                    }, 5);
                    frm.reload_doc();
                }
            });
        }
    );
}

function cancel_message(frm) {
    frappe.confirm(
        __('Are you sure you want to cancel this message?'),
        function() {
            frm.call('cancel_message').then(r => {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: r.message.message,
                        indicator: 'blue'
                    }, 5);
                    frm.reload_doc();
                }
            });
        }
    );
}

function format_message_preview(frm) {
    if (frm.doc.message) {
        // Show WhatsApp-style preview
        let preview_html = `
            <div class="whatsapp-message-preview mt-3">
                <label class="control-label">${__('Message Preview')}</label>
                <div class="whatsapp-bubble p-3 rounded" style="background: #DCF8C6; max-width: 400px; white-space: pre-wrap; font-family: system-ui, -apple-system, sans-serif; font-size: 14px;">
                    ${format_whatsapp_text(frm.doc.message)}
                </div>
            </div>
        `;
        
        // Insert after message field
        frm.fields_dict.message.$wrapper.after(preview_html);
    }
}

function format_whatsapp_text(text) {
    // Escape HTML first
    text = frappe.utils.escape_html(text);
    
    // Convert WhatsApp formatting to HTML
    // Bold: *text* -> <b>text</b>
    text = text.replace(/\*([^*]+)\*/g, '<b>$1</b>');
    // Italic: _text_ -> <i>text</i>
    text = text.replace(/_([^_]+)_/g, '<i>$1</i>');
    // Strikethrough: ~text~ -> <s>text</s>
    text = text.replace(/~([^~]+)~/g, '<s>$1</s>');
    // Monospace: `text` -> <code>text</code>
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    return text;
}

// List View settings
frappe.listview_settings['WhatsApp Message Log'] = {
    get_indicator: function(doc) {
        let colors = {
            'Pending': 'orange',
            'Queued': 'blue',
            'Sending': 'blue',
            'Sent': 'green',
            'Delivered': 'green',
            'Read': 'green',
            'Failed': 'red',
            'Cancelled': 'gray'
        };
        return [__(doc.status), colors[doc.status] || 'gray', 'status,=,' + doc.status];
    },
    
    formatters: {
        message: function(value) {
            if (value && value.length > 50) {
                return value.substring(0, 50) + '...';
            }
            return value;
        }
    }
};
