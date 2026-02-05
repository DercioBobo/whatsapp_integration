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
                show_preview_dialog(frm);
            }, __('Ações'));
        }

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
    }
});

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
