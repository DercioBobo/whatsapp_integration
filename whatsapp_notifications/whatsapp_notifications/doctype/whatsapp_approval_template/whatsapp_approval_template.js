// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Approval Template', {
    refresh: function(frm) {
        // Setup field selectors when form loads
        if (frm.doc.document_type) {
            setup_field_selector(frm, 'phone_field');
        }
    },

    document_type: function(frm) {
        // When document type changes, update field selectors
        if (frm.doc.document_type) {
            setup_field_selector(frm, 'phone_field');
        } else {
            // Clear the awesomplete data
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
                    // Build options for awesomplete
                    var options = fields.map(function(f) {
                        return {
                            label: f.label + ' (' + f.fieldname + ')',
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
                                label: f.label + ' (' + f.fieldname + ')',
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

function clear_field_selector(frm, fieldname) {
    var field = frm.get_field(fieldname);
    if (field && field.$input && field.$input.data('awesomplete')) {
        field.$input.data('awesomplete').list = [];
    }
}
