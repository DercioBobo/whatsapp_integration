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

// ============================================================
// Media Sending Functions
// ============================================================

/**
 * Send a WhatsApp message with media (document PDF or attachment)
 * @param {object} options - Send options
 */
frappe.whatsapp.send_media = function(options = {}) {
    return frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp_media',
        args: {
            phone: options.phone,
            doctype: options.doctype || null,
            docname: options.docname || null,
            file_url: options.file_url || null,
            print_format: options.print_format || null,
            caption: options.caption || null,
            queue: options.queue !== false
        },
        callback: function(r) {
            if (r.message) {
                if (r.message.success) {
                    frappe.show_alert({
                        message: __('WhatsApp media sent successfully'),
                        indicator: 'green'
                    }, 5);
                    if (options.callback) {
                        options.callback(r.message);
                    }
                } else {
                    frappe.msgprint({
                        title: __('WhatsApp Error'),
                        indicator: 'red',
                        message: r.message.error || __('Failed to send media')
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
                message: __('Failed to send WhatsApp media. Please check the Error Log.')
            });
            if (options.error_callback) {
                options.error_callback(err);
            }
        }
    });
};

/**
 * Open WhatsApp media compose dialog
 * @param {object} options - Dialog options (doctype, docname, phone, etc.)
 */
frappe.whatsapp.compose_media = function(options = {}) {
    let doctype = options.doctype;
    let docname = options.docname;
    let phone = options.phone || '';
    let caption = options.caption || '';
    let print_format = options.print_format || 'Standard';

    // First, get print formats and attachments
    let promises = [
        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications.api.get_print_formats',
            args: { doctype: doctype }
        }),
        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications.api.get_document_attachments',
            args: { doctype: doctype, docname: docname }
        })
    ];

    Promise.all(promises).then(function(results) {
        let print_formats_result = results[0].message;
        let attachments_result = results[1].message;

        let print_formats = print_formats_result.success ? print_formats_result.print_formats : [{name: 'Standard'}];
        let attachments = attachments_result.success ? attachments_result.attachments : [];

        // Build send type options
        let send_options = [
            { label: __('Document PDF'), value: 'pdf' }
        ];

        if (attachments.length > 0) {
            send_options.push({ label: __('Attachment'), value: 'attachment' });
        }

        // Build attachments select options
        let attachment_options = attachments.map(a => ({
            label: a.file_name + ' (' + frappe.whatsapp.format_file_size(a.file_size) + ')',
            value: a.file_url
        }));

        // Build print format options
        let pf_options = print_formats.map(p => p.name);

        let dialog = new frappe.ui.Dialog({
            title: __('Send via WhatsApp'),
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
                    fieldname: 'send_type',
                    fieldtype: 'Select',
                    label: __('What to Send'),
                    reqd: 1,
                    options: send_options.map(o => o.value).join('\n'),
                    default: 'pdf',
                    onchange: function() {
                        let val = dialog.get_value('send_type');
                        dialog.set_df_property('print_format', 'hidden', val !== 'pdf');
                        dialog.set_df_property('attachment', 'hidden', val !== 'attachment');
                    }
                },
                {
                    fieldname: 'print_format',
                    fieldtype: 'Select',
                    label: __('Print Format'),
                    options: pf_options.join('\n'),
                    default: print_format,
                    depends_on: "eval:doc.send_type=='pdf'"
                },
                {
                    fieldname: 'attachment',
                    fieldtype: 'Select',
                    label: __('Select Attachment'),
                    options: attachment_options.map(a => a.value).join('\n'),
                    default: attachments.length > 0 ? attachments[0].file_url : '',
                    hidden: 1,
                    depends_on: "eval:doc.send_type=='attachment'"
                },
                {
                    fieldname: 'caption',
                    fieldtype: 'Small Text',
                    label: __('Caption'),
                    default: caption || __('Document: {0}', [docname])
                }
            ],
            primary_action_label: __('Send WhatsApp'),
            primary_action: function(values) {
                dialog.get_primary_btn().prop('disabled', true).html(__('Sending...'));

                let send_options = {
                    phone: values.phone,
                    doctype: doctype,
                    docname: docname,
                    caption: values.caption,
                    callback: function() {
                        dialog.hide();
                        frappe.show_alert({
                            message: __('WhatsApp media sent successfully'),
                            indicator: 'green'
                        }, 5);
                        if (options.callback) {
                            options.callback();
                        }
                    },
                    error_callback: function() {
                        dialog.get_primary_btn().prop('disabled', false).html(__('Send WhatsApp'));
                    }
                };

                if (values.send_type === 'pdf') {
                    send_options.print_format = values.print_format;
                } else if (values.send_type === 'attachment') {
                    send_options.file_url = values.attachment;
                }

                frappe.whatsapp.send_media(send_options);
            }
        });

        dialog.show();

        // Update visibility based on initial selection
        setTimeout(function() {
            let val = dialog.get_value('send_type');
            dialog.set_df_property('print_format', 'hidden', val !== 'pdf');
            dialog.set_df_property('attachment', 'hidden', val !== 'attachment');
        }, 100);
    });
};

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
frappe.whatsapp.format_file_size = function(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

/**
 * Get phone value from document using field path (supports dot notation)
 * @param {object} doc - Document object
 * @param {string} field_path - Field path (e.g., "contact_mobile" or "customer.mobile_no")
 * @returns {string} Phone value or empty string
 */
frappe.whatsapp.get_phone_from_doc = function(doc, field_path) {
    if (!field_path) return '';

    let parts = field_path.split('.');
    let value = doc;

    for (let part of parts) {
        if (value && typeof value === 'object') {
            value = value[part];
        } else {
            return '';
        }
    }

    return value || '';
};

// ============================================================
// Auto-add WhatsApp Media Button to Configured DocTypes
// ============================================================

// Cache for enabled doctypes
frappe.whatsapp._media_doctypes_cache = null;
frappe.whatsapp._media_doctypes_loading = false;

/**
 * Load list of enabled media doctypes
 */
frappe.whatsapp.load_media_doctypes = function(callback) {
    if (frappe.whatsapp._media_doctypes_cache) {
        if (callback) callback(frappe.whatsapp._media_doctypes_cache);
        return;
    }

    if (frappe.whatsapp._media_doctypes_loading) {
        // Wait and retry
        setTimeout(function() {
            frappe.whatsapp.load_media_doctypes(callback);
        }, 100);
        return;
    }

    frappe.whatsapp._media_doctypes_loading = true;

    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_all_media_doctypes',
        async: true,
        callback: function(r) {
            frappe.whatsapp._media_doctypes_loading = false;
            if (r.message && r.message.success) {
                frappe.whatsapp._media_doctypes_cache = r.message.doctypes || [];
            } else {
                frappe.whatsapp._media_doctypes_cache = [];
            }
            if (callback) callback(frappe.whatsapp._media_doctypes_cache);
        }
    });
};

/**
 * Add WhatsApp media button to form if doctype is enabled
 * @param {object} frm - Frappe form object
 */
frappe.whatsapp.maybe_add_media_button = function(frm) {
    if (frm.is_new()) return;

    frappe.whatsapp.load_media_doctypes(function(doctypes) {
        if (doctypes.includes(frm.doctype)) {
            // Get config for this doctype
            frappe.call({
                method: 'whatsapp_notifications.whatsapp_notifications.api.get_media_doctype_config',
                args: { doctype: frm.doctype },
                async: true,
                callback: function(r) {
                    if (r.message && r.message.enabled) {
                        let config = r.message;

                        // Get phone from configured field
                        let phone = '';
                        if (config.phone_field) {
                            phone = frappe.whatsapp.get_phone_from_doc(frm.doc, config.phone_field);
                        }

                        // Build default caption from template if provided
                        let caption = '';
                        if (config.caption_template) {
                            try {
                                caption = frappe.render(config.caption_template, { doc: frm.doc });
                            } catch (e) {
                                caption = __('Document: {0}', [frm.docname]);
                            }
                        }

                        // Remove existing button if any (to avoid duplicates)
                        frm.remove_custom_button(__('Send via WhatsApp'), __('Actions'));

                        // Add the button
                        frm.add_custom_button(__('Send via WhatsApp'), function() {
                            frappe.whatsapp.compose_media({
                                doctype: frm.doctype,
                                docname: frm.docname,
                                phone: phone,
                                caption: caption,
                                print_format: config.default_print_format || 'Standard',
                                callback: function() {
                                    frm.reload_doc();
                                }
                            });
                        }, __('Actions'));
                    }
                }
            });
        }
    });
};

// ============================================================
// Global Form Hook
// ============================================================

// Hook into form refresh to add WhatsApp media button
$(document).on('form-refresh', function(e, frm) {
    if (frm && !frm.is_new()) {
        frappe.whatsapp.maybe_add_media_button(frm);
    }
});

// Initialize on page load
$(document).ready(function() {
    // Preload media doctypes list
    frappe.whatsapp.load_media_doctypes();
});
