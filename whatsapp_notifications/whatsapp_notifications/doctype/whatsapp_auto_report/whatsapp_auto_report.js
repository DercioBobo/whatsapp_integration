// Copyright (c) 2024, Entretech and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Auto Report', {
    refresh: function (frm) {
        // Add Send Now button
        if (!frm.is_new()) {
            frm.add_custom_button(__('Enviar Agora'), function () {
                frappe.confirm(
                    __('Enviar este relatório agora para todos os destinatários?'),
                    function () {
                        frm.call({
                            method: 'generate_and_send',
                            doc: frm.doc,
                            freeze: true,
                            freeze_message: __('Gerando e enviando relatório...'),
                            callback: function (r) {
                                if (r.message) {
                                    if (r.message.success) {
                                        frappe.show_alert({
                                            message: __('Relatório enviado para {0} destinatário(s)', [r.message.sent]),
                                            indicator: 'green'
                                        }, 5);
                                        frm.reload_doc();
                                    } else if (r.message.skipped) {
                                        frappe.show_alert({
                                            message: __('Relatório não enviado: {0}', [r.message.reason]),
                                            indicator: 'orange'
                                        }, 5);
                                    } else {
                                        frappe.msgprint({
                                            title: __('Erro'),
                                            indicator: 'red',
                                            message: r.message.error || __('Falha ao enviar relatório')
                                        });
                                    }
                                }
                            }
                        });
                    }
                );
            }, __('Ações'));

            frm.add_custom_button(__('Pré-visualizar'), function () {
                if (frm.doc.source === 'Document List') {
                    show_document_list_preview(frm);
                } else {
                    show_preview_dialog(frm);
                }
            }, __('Ações'));
        }

        if (frm.doc.source === 'Document List' && frm.doc.list_doctype) {
            load_split_options(frm);
        }
        frm._last_group_id = frm.doc.group_id;

        // Show last status indicator
        if (frm.doc.last_status) {
            let indicator = 'blue';
            if (frm.doc.last_status.includes('Sent')) {
                indicator = 'green';
            } else if (frm.doc.last_status.includes('Failed') || frm.doc.last_status.includes('Error')) {
                indicator = 'red';
            } else if (frm.doc.last_status.includes('Skipped')) {
                indicator = 'orange';
            }

            frm.dashboard.add_indicator(__('Último status: {0}', [frm.doc.last_status]), indicator);
        }
    },

    report: function (frm) {
        // Clear filters when report changes
        frm.set_value('filters', '');
    },

    source: function (frm) {
        if (frm.doc.source === 'Document List' && frm.doc.list_doctype) {
            load_split_options(frm);
        }
    },

    list_doctype: function (frm) {
        frm.set_value('list_filters', '');
        frm.set_value('split_by_field', '');
        frm.set_value('split_phone_field', '');
        if (frm.doc.list_doctype) {
            load_split_options(frm);
        }
    },

    edit_list_filters_button: function (frm) {
        frappe.whatsapp.edit_filters(frm, {
            doctype: frm.doc.list_doctype,
            field: 'list_filters',
            title: __('Que documentos de {0} incluir?', [__(frm.doc.list_doctype || '')])
        });
    },

    select_group_button: function (frm) {
        frappe.whatsapp.pick_group(frm, { id_field: 'group_id', name_field: 'group_name' });
    },

    select_mentions_button: function (frm) {
        frappe.whatsapp.pick_group_members(frm, {
            group_field: 'group_id', group_name_field: 'group_name', mentions_field: 'group_mentions'
        });
    },

    group_id: function (frm) {
        // Members picked for a previous group don't belong to the new one
        if (frm.doc.group_mentions && frm._last_group_id && frm._last_group_id !== frm.doc.group_id) {
            frm.set_value('group_mentions', '');
            frappe.show_alert({ message: __('Grupo alterado: membros marcados foram limpos'), indicator: 'orange' }, 4);
        }
        frm._last_group_id = frm.doc.group_id;
    }
});

// ─── Document List ────────────────────────────────────────────────────────────

function load_split_options(frm) {
    frappe.call({
        method: 'whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_auto_report.whatsapp_auto_report.get_split_options',
        args: { doctype: frm.doc.list_doctype },
        callback: function (r) {
            let options = [{ label: __('— Não dividir —'), value: '' }].concat(r.message || []);
            frm.set_df_property('split_by_field', 'options', options);
            frm.refresh_field('split_by_field');
        }
    });
}

function show_document_list_preview(frm) {
    frm.call({
        method: 'preview_document_list',
        doc: frm.doc,
        freeze: true,
        freeze_message: __('A gerar pré-visualização...'),
        callback: function (r) {
            if (!r.message) return;
            let p = r.message;
            let esc = frappe.utils.escape_html;
            let kind_label = { fixed: __('Destinatário'), group: __('Grupo'), person: __('Pessoal') };
            let kind_color = { fixed: 'blue', group: 'green', person: 'orange' };

            let body = p.messages.length ? p.messages.map(m => `
                <div class="mb-3 p-2 border rounded">
                    <div class="small mb-1 d-flex flex-wrap align-items-center" style="gap:10px;">
                        <span class="indicator-pill ${kind_color[m.kind]}">${kind_label[m.kind]}</span>
                        <b>${esc(m.label)}</b>
                        <span class="text-muted">${__('{0} documento(s)', [m.count])}</span>
                        ${m.mention_everyone ? `<span class="indicator-pill blue">${__('Marca todos')}</span>` : ''}
                    </div>
                    <div style="background:#DCF8C6;padding:8px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;">${frappe.whatsapp.render_tags(m.message || '', p.mention_names || {})}</div>
                </div>`).join('')
                : `<p class="text-muted">${__('Nada a enviar: nenhum documento corresponde aos filtros.')}</p>`;

            if (p.split_hidden) {
                body += `<p class="text-muted small">${__('…e mais {0} mensagem(ns) pessoal(is)', [p.split_hidden])}</p>`;
            }
            if (p.missing_phone.length) {
                body += `<div class="alert alert-warning small mt-2">${__('Sem número de telefone (não receberão)')}: ${esc(p.missing_phone.join(', '))}</div>`;
            }

            let total = p.messages.length + (p.split_hidden || 0);
            frappe.msgprint({
                title: __('Pré-visualização · {0} mensagem(ns)', [total]),
                message: body,
                wide: true
            });
        }
    });
}

function show_preview_dialog(frm) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Report',
            filters: { name: frm.doc.report },
            fieldname: ['ref_doctype', 'report_type']
        },
        callback: function (r) {
            if (r.message) {
                // Build preview
                let filters = {};
                try {
                    if (frm.doc.filters) {
                        filters = JSON.parse(frm.doc.filters);
                    }
                } catch (e) { }

                let preview_html = `
                    <div class="preview-container">
                        <h5>${__('Configuração do Relatório')}</h5>
                        <table class="table table-bordered">
                            <tr><td><strong>${__('Relatório')}</strong></td><td>${frm.doc.report}</td></tr>
                            <tr><td><strong>${__('Tipo')}</strong></td><td>${r.message.report_type}</td></tr>
                            <tr><td><strong>${__('Frequência')}</strong></td><td>${frm.doc.frequency}</td></tr>
                            <tr><td><strong>${__('Horário')}</strong></td><td>${frm.doc.send_time}</td></tr>
                            <tr><td><strong>${__('Filtros')}</strong></td><td><pre>${JSON.stringify(filters, null, 2)}</pre></td></tr>
                            <tr><td><strong>${__('Destinatários')}</strong></td><td><pre>${frm.doc.recipients || 'Nenhum'}</pre></td></tr>
                        </table>
                        <h5>${__('Anexos')}</h5>
                        <ul>
                            ${frm.doc.include_excel ? '<li>Excel (.xlsx)</li>' : ''}
                            ${frm.doc.include_pdf ? '<li>PDF</li>' : ''}
                            ${!frm.doc.include_excel && !frm.doc.include_pdf ? '<li>Apenas mensagem de texto</li>' : ''}
                        </ul>
                    </div>
                `;

                frappe.msgprint({
                    title: __('Pré-visualização'),
                    message: preview_html,
                    wide: true
                });
            }
        }
    });
}
