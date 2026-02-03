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

        // Build send type options with clearer labels
        let send_type_options = [];

        // Always add Document PDF option
        send_type_options.push('Document PDF');

        // Add attachment option if there are attachments
        if (attachments.length > 0) {
            send_type_options.push('Attached File');
        }

        // Build attachments select options with labels
        let attachment_labels = attachments.map(a =>
            a.file_name + ' (' + frappe.whatsapp.format_file_size(a.file_size) + ')'
        );

        // Build print format options
        let pf_options = print_formats.map(p => p.name);

        // Default to first available option
        let default_send_type = send_type_options[0] || 'Document PDF';

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
                    options: send_type_options.join('\n'),
                    default: default_send_type,
                    onchange: function() {
                        let val = dialog.get_value('send_type');
                        dialog.set_df_property('print_format', 'hidden', val !== 'Document PDF');
                        dialog.set_df_property('attachment', 'hidden', val !== 'Attached File');
                    }
                },
                {
                    fieldname: 'print_format',
                    fieldtype: 'Select',
                    label: __('Print Format'),
                    options: pf_options.join('\n'),
                    default: print_format,
                    depends_on: "eval:doc.send_type=='Document PDF'"
                },
                {
                    fieldname: 'attachment',
                    fieldtype: 'Select',
                    label: __('Select File'),
                    options: attachments.map(a => a.file_url).join('\n'),
                    default: attachments.length > 0 ? attachments[0].file_url : '',
                    hidden: 1,
                    depends_on: "eval:doc.send_type=='Attached File'",
                    description: attachments.length > 0 ? attachment_labels.join(', ') : ''
                },
                {
                    fieldname: 'caption',
                    fieldtype: 'Small Text',
                    label: __('Caption (optional)'),
                    default: caption || __('Document: {0}', [docname])
                }
            ],
            primary_action_label: __('Send WhatsApp'),
            primary_action: function(values) {
                dialog.get_primary_btn().prop('disabled', true).html(__('Sending...'));

                let media_options = {
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

                if (values.send_type === 'Document PDF') {
                    media_options.print_format = values.print_format;
                } else if (values.send_type === 'Attached File') {
                    media_options.file_url = values.attachment;
                }

                frappe.whatsapp.send_media(media_options);
            }
        });

        dialog.show();

        // Update visibility based on initial selection
        setTimeout(function() {
            let val = dialog.get_value('send_type');
            dialog.set_df_property('print_format', 'hidden', val !== 'Document PDF');
            dialog.set_df_property('attachment', 'hidden', val !== 'Attached File');
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
    // Preload approval templates list
    frappe.whatsapp.load_approval_templates();
});

// ============================================================
// Approval Functions
// ============================================================

// Cache for approval templates
frappe.whatsapp._approval_templates_cache = {};
frappe.whatsapp._approval_templates_loading = {};

/**
 * Load approval templates for a doctype
 * @param {string} doctype - Document type
 * @param {function} callback - Callback with templates list
 * @param {boolean} manual_only - If true, only return templates with manual trigger enabled
 */
frappe.whatsapp.load_approval_templates = function(doctype, callback, manual_only) {
    if (!doctype) {
        // Just initialize the cache
        if (callback) callback([]);
        return;
    }

    var cache_key = doctype + (manual_only ? '_manual' : '');

    if (frappe.whatsapp._approval_templates_cache[cache_key]) {
        if (callback) callback(frappe.whatsapp._approval_templates_cache[cache_key]);
        return;
    }

    if (frappe.whatsapp._approval_templates_loading[cache_key]) {
        // Wait and retry
        setTimeout(function() {
            frappe.whatsapp.load_approval_templates(doctype, callback, manual_only);
        }, 100);
        return;
    }

    frappe.whatsapp._approval_templates_loading[cache_key] = true;

    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_approval_templates',
        args: {
            doctype: doctype,
            manual_only: manual_only ? 1 : 0
        },
        async: true,
        callback: function(r) {
            frappe.whatsapp._approval_templates_loading[cache_key] = false;
            if (r.message && r.message.success) {
                frappe.whatsapp._approval_templates_cache[cache_key] = r.message.templates || [];
            } else {
                frappe.whatsapp._approval_templates_cache[cache_key] = [];
            }
            if (callback) callback(frappe.whatsapp._approval_templates_cache[cache_key]);
        }
    });
};

/**
 * Send an approval request
 * @param {object} options - Options (doctype, docname, template_name, phone, callback)
 */
frappe.whatsapp.send_approval = function(options = {}) {
    return frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.send_approval',
        args: {
            doctype: options.doctype,
            docname: options.docname,
            template_name: options.template_name,
            phone: options.phone || null
        },
        callback: function(r) {
            if (r.message) {
                if (r.message.success) {
                    frappe.show_alert({
                        message: __('Approval request sent successfully'),
                        indicator: 'green'
                    }, 5);
                    if (options.callback) {
                        options.callback(r.message);
                    }
                } else {
                    frappe.msgprint({
                        title: __('Approval Error'),
                        indicator: 'red',
                        message: r.message.error || __('Failed to send approval request')
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
                message: __('Failed to send approval request. Please check the Error Log.')
            });
            if (options.error_callback) {
                options.error_callback(err);
            }
        }
    });
};

/**
 * Open approval request dialog
 * @param {object} options - Dialog options (doctype, docname, callback)
 */
frappe.whatsapp.request_approval = function(options = {}) {
    let doctype = options.doctype;
    let docname = options.docname;

    // Get available templates for this doctype
    frappe.whatsapp.load_approval_templates(doctype, function(templates) {
        if (!templates || templates.length === 0) {
            frappe.msgprint({
                title: __('No Approval Templates'),
                indicator: 'orange',
                message: __('No approval templates are configured for {0}. Please create a WhatsApp Approval Template first.', [doctype])
            });
            return;
        }

        let template_options = templates.map(t => t.template_name).join('\n');
        let default_template = templates[0].template_name;

        let dialog = new frappe.ui.Dialog({
            title: __('Send for WhatsApp Approval'),
            fields: [
                {
                    fieldname: 'template',
                    fieldtype: 'Select',
                    label: __('Approval Template'),
                    reqd: 1,
                    options: template_options,
                    default: default_template
                },
                {
                    fieldname: 'phone',
                    fieldtype: 'Data',
                    label: __('Phone Number (optional)'),
                    description: __('Leave empty to use the phone number configured in the template')
                }
            ],
            primary_action_label: __('Send Approval Request'),
            primary_action: function(values) {
                dialog.get_primary_btn().prop('disabled', true).html(__('Sending...'));

                frappe.whatsapp.send_approval({
                    doctype: doctype,
                    docname: docname,
                    template_name: values.template,
                    phone: values.phone || null,
                    callback: function(result) {
                        dialog.hide();
                        if (options.callback) {
                            options.callback(result);
                        }
                    },
                    error_callback: function() {
                        dialog.get_primary_btn().prop('disabled', false).html(__('Send Approval Request'));
                    }
                });
            }
        });

        dialog.show();
    });
};

/**
 * Get pending approvals for a document
 * @param {string} doctype - Document type
 * @param {string} docname - Document name
 * @param {function} callback - Callback with approvals list
 */
frappe.whatsapp.get_pending_approvals = function(doctype, docname, callback) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_pending_approvals',
        args: {
            doctype: doctype,
            docname: docname
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                if (callback) callback(r.message.approvals || []);
            } else {
                if (callback) callback([]);
            }
        }
    });
};

/**
 * Cancel a pending approval request
 * @param {string} approval_request_name - Approval request name
 * @param {function} callback - Callback on success
 */
frappe.whatsapp.cancel_approval = function(approval_request_name, callback) {
    frappe.confirm(
        __('Are you sure you want to cancel this approval request?'),
        function() {
            frappe.call({
                method: 'whatsapp_notifications.whatsapp_notifications.api.cancel_approval',
                args: {
                    approval_request_name: approval_request_name
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Approval request cancelled'),
                            indicator: 'green'
                        }, 5);
                        if (callback) callback();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: r.message.error || __('Failed to cancel approval request')
                        });
                    }
                }
            });
        }
    );
};

/**
 * Add approval button to form if templates exist for this doctype (with manual trigger enabled)
 * @param {object} frm - Frappe form object
 */
frappe.whatsapp.maybe_add_approval_button = function(frm) {
    if (frm.is_new()) return;

    // Only load templates that have manual trigger enabled
    frappe.whatsapp.load_approval_templates(frm.doctype, function(templates) {
        if (templates && templates.length > 0) {
            // Remove existing button if any (to avoid duplicates)
            frm.remove_custom_button(__('Send for Approval'), __('WhatsApp'));

            // Add the button
            frm.add_custom_button(__('Send for Approval'), function() {
                frappe.whatsapp.request_approval({
                    doctype: frm.doctype,
                    docname: frm.docname,
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('WhatsApp'));
        }
    }, true);  // manual_only = true
};

// Hook into form refresh to add WhatsApp approval button
$(document).on('form-refresh', function(e, frm) {
    if (frm && !frm.is_new()) {
        frappe.whatsapp.maybe_add_approval_button(frm);
    }
});
