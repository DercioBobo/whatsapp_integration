/**
 * WhatsApp Notifications for ERPNext
 * Client-side utilities and global functions
 */

// Global namespace
frappe.whatsapp = frappe.whatsapp || {};

/**
 * Send a WhatsApp message via API
 * @param {string} phone - Recipient phone number
 * @param {string} message - Message content
 * @param {object} options - Additional options (doctype, docname, callback)
 */
frappe.whatsapp.send = function(phone, message, options = {}) {
    return frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp',
        args: {
            phone: phone,
            message: message,
            doctype: options.doctype || null,
            docname: options.docname || null,
            queue: options.queue !== false
        },
        callback: function(r) {
            if (r.message) {
                if (r.message.success) {
                    frappe.show_alert({
                        message: __('WhatsApp message sent successfully'),
                        indicator: 'green'
                    }, 5);
                    if (options.callback) {
                        options.callback(r.message);
                    }
                } else {
                    frappe.msgprint({
                        title: __('WhatsApp Error'),
                        indicator: 'red',
                        message: r.message.error || __('Failed to send message')
                    });
                    if (options.error_callback) {
                        options.error_callback(r.message);
                    }
                }
            }
        },
        error: function(err) {
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Failed to send WhatsApp message. Please check the Error Log.')
            });
            if (options.error_callback) {
                options.error_callback(err);
            }
        }
    });
};

/**
 * Open a WhatsApp compose dialog
 * @param {object} options - Dialog options
 */
frappe.whatsapp.compose = function(options = {}) {
    let default_message = options.message || '';
    let phone = options.phone || '';
    let doctype = options.doctype || null;
    let docname = options.docname || null;
    
    let dialog = new frappe.ui.Dialog({
        title: __('Send WhatsApp Message'),
        size: 'large',
        fields: [
            {
                fieldname: 'phone',
                fieldtype: 'Data',
                label: __('Phone Number'),
                reqd: 1,
                default: phone
            },
            {
                fieldname: 'message',
                fieldtype: 'Text',
                label: __('Message'),
                reqd: 1,
                default: default_message
            },
            {
                fieldname: 'preview_section',
                fieldtype: 'Section Break',
                label: __('Preview'),
                collapsible: 1
            },
            {
                fieldname: 'preview_html',
                fieldtype: 'HTML',
                options: '<div class="whatsapp-preview p-3 rounded" style="background: #DCF8C6; white-space: pre-wrap;"></div>'
            }
        ],
        primary_action_label: __('Send'),
        primary_action: function(values) {
            dialog.get_primary_btn().prop('disabled', true).html(__('Sending...'));
            
            frappe.whatsapp.send(values.phone, values.message, {
                doctype: doctype,
                docname: docname,
                callback: function() {
                    dialog.hide();
                    if (options.callback) {
                        options.callback();
                    }
                },
                error_callback: function() {
                    dialog.get_primary_btn().prop('disabled', false).html(__('Send'));
                }
            });
        }
    });
    
    // Update preview when message changes
    dialog.fields_dict.message.$input.on('input', function() {
        let text = $(this).val();
        let preview = dialog.$wrapper.find('.whatsapp-preview');
        preview.text(text);
    });
    
    dialog.show();
    
    // Initial preview
    if (default_message) {
        dialog.$wrapper.find('.whatsapp-preview').text(default_message);
    }
    
    return dialog;
};

/**
 * Format phone number for display
 * @param {string} phone - Raw phone number
 * @returns {string} Formatted phone number
 */
frappe.whatsapp.format_phone = function(phone) {
    if (!phone) return '';
    
    // Remove non-digits
    let cleaned = String(phone).replace(/\D/g, '');
    
    // Add + if starts with country code
    if (cleaned.length > 9) {
        return '+' + cleaned;
    }
    
    return cleaned;
};

/**
 * Add WhatsApp button to a form
 * @param {object} frm - Frappe form object
 * @param {string} phone_field - Field name containing phone number
 * @param {function} message_builder - Function that returns the default message
 */
frappe.whatsapp.add_form_button = function(frm, phone_field, message_builder) {
    if (frm.is_new()) return;
    
    let phone = frm.doc[phone_field];
    if (!phone) return;
    
    frm.add_custom_button(__('WhatsApp'), function() {
        let message = typeof message_builder === 'function' 
            ? message_builder(frm.doc) 
            : (message_builder || '');
        
        frappe.whatsapp.compose({
            phone: phone,
            message: message,
            doctype: frm.doctype,
            docname: frm.docname,
            callback: function() {
                frm.reload_doc();
            }
        });
    }, __('Actions')).addClass('btn-success');
};

// Extend String prototype for WhatsApp formatting
if (!String.prototype.waFormat) {
    String.prototype.waFormat = function(type) {
        switch(type) {
            case 'bold':
                return '*' + this + '*';
            case 'italic':
                return '_' + this + '_';
            case 'strike':
                return '~' + this + '~';
            case 'code':
                return '`' + this + '`';
            default:
                return this;
        }
    };
}

// Initialize on page load
$(document).ready(function() {
    // Nothing to initialize globally
});
