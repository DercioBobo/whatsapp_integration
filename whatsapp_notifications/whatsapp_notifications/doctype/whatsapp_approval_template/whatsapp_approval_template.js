// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Approval Template', {
    refresh: function(frm) {
        // Enable inline (in-place) editing on the response options grid
        frm.fields_dict.response_options.grid.in_place_edit = true;

        if (frm.doc.document_type) {
            setup_field_selector(frm, 'phone_field');
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__('Preview Message'), function() {
                preview_approval_message(frm);
            });
        }
    },

    document_type: function(frm) {
        if (frm.doc.document_type) {
            setup_field_selector(frm, 'phone_field');
        } else {
            clear_field_selector(frm, 'phone_field');
        }
    }
});

frappe.ui.form.on('WhatsApp Approval Option', {
    action_type: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.action_type === 'Update Field' && frm.doc.document_type) {
            setup_child_field_selector(frm, cdt, cdn, 'field_to_update');
        }
    }
});

function setup_field_selector(frm, fieldname) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_doctype_fields',
        args: {
            doctype: frm.doc.document_type
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                var fields = r.message.fields;
                var field = frm.get_field(fieldname);

                if (field && field.$input) {
                    // Build options for awesomplete — show all fields with their type
                    var options = fields.map(function(f) {
                        return {
                            label: f.label + ' (' + f.fieldname + ') [' + f.fieldtype + ']',
                            value: f.fieldname
                        };
                    });

                    // Setup awesomplete
                    if (field.$input.data('awesomplete')) {
                        field.$input.data('awesomplete').list = options;
                    } else {
                        var awesomplete = new Awesomplete(field.$input.get(0), {
                            minChars: 0,
                            maxItems: 20,
                            list: options,
                            filter: function(text, input) {
                                var inputLower = input.toLowerCase();
                                return text.label.toLowerCase().includes(inputLower) ||
                                       text.value.toLowerCase().includes(inputLower);
                            },
                            item: function(text, input) {
                                return Awesomplete.$.create("li", {
                                    innerHTML: text.label,
                                    "aria-selected": "false"
                                });
                            },
                            replace: function(text) {
                                this.input.value = text.value;
                            }
                        });

                        field.$input.data('awesomplete', awesomplete);

                        // Show all options on focus
                        field.$input.on('focus', function() {
                            if (awesomplete.ul.childNodes.length === 0) {
                                awesomplete.evaluate();
                            }
                            awesomplete.open();
                        });
                    }
                }
            }
        }
    });
}

function setup_child_field_selector(frm, cdt, cdn, fieldname) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.api.get_doctype_fields',
        args: {
            doctype: frm.doc.document_type
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                var fields = r.message.fields;
                var grid_row = frm.fields_dict.response_options.grid.grid_rows_by_docname[cdn];

                if (grid_row) {
                    var field = grid_row.get_field(fieldname);

                    if (field && field.$input) {
                        var options = fields.map(function(f) {
                            return {
                                label: f.label + ' (' + f.fieldname + ') [' + f.fieldtype + ']',
                                value: f.fieldname
                            };
                        });

                        if (field.$input.data('awesomplete')) {
                            field.$input.data('awesomplete').list = options;
                        } else {
                            var awesomplete = new Awesomplete(field.$input.get(0), {
                                minChars: 0,
                                maxItems: 20,
                                list: options,
                                filter: function(text, input) {
                                    var inputLower = input.toLowerCase();
                                    return text.label.toLowerCase().includes(inputLower) ||
                                           text.value.toLowerCase().includes(inputLower);
                                },
                                item: function(text, input) {
                                    return Awesomplete.$.create("li", {
                                        innerHTML: text.label,
                                        "aria-selected": "false"
                                    });
                                },
                                replace: function(text) {
                                    this.input.value = text.value;
                                }
                            });

                            field.$input.data('awesomplete', awesomplete);

                            field.$input.on('focus', function() {
                                if (awesomplete.ul.childNodes.length === 0) {
                                    awesomplete.evaluate();
                                }
                                awesomplete.open();
                            });
                        }
                    }
                }
            }
        }
    });
}

function preview_approval_message(frm) {
    if (!frm.doc.message_template) {
        frappe.msgprint(__('Please add a message template first'));
        return;
    }
    if (!frm.doc.response_options || !frm.doc.response_options.length) {
        frappe.msgprint(__('Please add at least one response option first'));
        return;
    }

    frappe.prompt([
        {
            fieldname: 'docname',
            fieldtype: 'Link',
            options: frm.doc.document_type,
            label: __('Document to Preview With'),
            reqd: 1
        }
    ], function(values) {
        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications.api.preview_approval_message',
            args: {
                template_name: frm.doc.name,
                docname: values.docname
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    let escaped = $('<div>').text(r.message.message).html();
                    let d = new frappe.ui.Dialog({
                        title: __('Message Preview'),
                        fields: [{
                            fieldtype: 'HTML',
                            options: '<pre style="white-space:pre-wrap;background:#f8f9fa;padding:15px;border-radius:6px;border:1px solid #dee2e6;font-size:13px;">' + escaped + '</pre>'
                        }]
                    });
                    d.show();
                } else {
                    frappe.msgprint({
                        title: __('Preview Error'),
                        message: r.message ? frappe.utils.escape_html(r.message.error) : __('Unknown error'),
                        indicator: 'red'
                    });
                }
            }
        });
    }, __('Preview Approval Message'), __('Preview'));
}

function clear_field_selector(frm, fieldname) {
    var field = frm.get_field(fieldname);
    if (field && field.$input && field.$input.data('awesomplete')) {
        field.$input.data('awesomplete').list = [];
    }
}
