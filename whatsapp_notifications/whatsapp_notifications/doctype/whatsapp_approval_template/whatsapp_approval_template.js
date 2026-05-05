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

function render_whatsapp_text(text) {
    let html = $('<div>').text(text).html();
    // WhatsApp markdown: bold, italic, strikethrough, monospace (multi-line then single-line)
    html = html
        .replace(/```([\s\S]+?)```/g, '<code style="font-family:monospace;background:rgba(0,0,0,.08);padding:1px 4px;border-radius:3px;font-size:13px;">$1</code>')
        .replace(/`([^`\n]+)`/g, '<code style="font-family:monospace;background:rgba(0,0,0,.08);padding:1px 4px;border-radius:3px;font-size:13px;">$1</code>')
        .replace(/\*([^\*\n]+)\*/g, '<strong>$1</strong>')
        .replace(/_([^_\n]+)_/g, '<em>$1</em>')
        .replace(/~([^~\n]+)~/g, '<del>$1</del>')
        .replace(/\n/g, '<br>');
    return html;
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
                    let formatted = render_whatsapp_text(r.message.message);
                    let now = new Date();
                    let time = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

                    let html = `
                        <div style="background:#e5ddd5;padding:16px 20px;border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
                            <div style="display:flex;justify-content:flex-end;">
                                <div style="background:#dcf8c6;border-radius:8px 0 8px 8px;padding:8px 12px 6px 12px;max-width:85%;box-shadow:0 1px 0.5px rgba(0,0,0,.18);">
                                    <div style="font-size:14px;line-height:1.5;color:#111b21;word-break:break-word;">${formatted}</div>
                                    <div style="font-size:11px;color:#667781;text-align:right;margin-top:4px;">${time}&nbsp;✓✓</div>
                                </div>
                            </div>
                        </div>`;

                    let d = new frappe.ui.Dialog({
                        title: __('Message Preview'),
                        fields: [{ fieldtype: 'HTML', options: html }],
                        size: 'large'
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
