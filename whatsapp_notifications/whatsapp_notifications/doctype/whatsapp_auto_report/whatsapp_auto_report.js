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
                show_messages_preview(frm, frm.doc.source === 'Document List' ? 'preview_document_list' : 'preview_report');
            }, __('Ações'));
        }

        if (frm.doc.source === 'Document List' && frm.doc.list_doctype) {
            load_split_options(frm);
        }
        describe_list_filters(frm);
        setup_list_template_help(frm);
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
        describe_list_filters(frm);
        setup_list_template_help(frm);
    },

    list_doctype: function (frm) {
        frm.set_value('list_filters', '');
        frm.set_value('split_by_field', '');
        frm.set_value('split_phone_field', '');
        if (frm.doc.list_doctype) {
            load_split_options(frm);
        }
        describe_list_filters(frm);
        setup_list_template_help(frm);
    },

    split_by_field: function (frm) {
        setup_list_template_help(frm);
    },

    include_link: function (frm) {
        setup_list_template_help(frm);
    },

    list_filters: function (frm) {
        describe_list_filters(frm);
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

    group_mentions: function (frm) {
        setup_list_template_help(frm);
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
        // Group removed: nothing left to tag
        if (!frm.doc.group_id && frm.doc.mention_everyone) {
            frm.set_value('mention_everyone', 0);
        }
        frm._last_group_id = frm.doc.group_id;
        setup_list_template_help(frm);
    }
});

// ─── Document List ────────────────────────────────────────────────────────────

function setup_list_template_help(frm) {
    let is_list = frm.doc.source === 'Document List';
    if (!is_list) return setup_report_template_help(frm);
    frappe.whatsapp.template_helper(frm, {
        field: 'message_template',
        doctype: is_list ? frm.doc.list_doctype : null,
        mode: 'list',
        tag_keys: frm.doc.group_id ? () => frappe.whatsapp.tag_keys(frm, 'group_mentions') : null,
        variables: [
            ['{% for d in docs %}…{% endfor %}', __('Loop over the listed documents (use d.field inside)')],
            ['{{ count }}', __('Number of matching documents (all, not only the listed ones)')],
            ['{{ more }}', __('How many were not listed')],
            ["{{ total('outstanding_amount') }}", __('Sum of a numeric field over all matching documents')],
            ['{{ recipient_name }}', __('Person receiving it (when using Split by)')],
            ['{{ report_name }}', __('This report\'s name')],
            ['{{ format_date(date) }}', __('Today\'s date')],
            ['{{ link }}', __('Link to the list in ERPNext with the same filters (per person when using Split by)')],
            ['{{ mentions }}', __('Tags for group members')],
            ["{{ tag('supervisor') }}", __('Tag one person by role (set roles in Select Members to Tag)')],
        ],
        snippets: function (ctx) {
            let title = ctx.title ? ` — {{ d.${ctx.title} }}` : '';
            let amount = ctx.amount_df ? frappe.whatsapp.field_expr(ctx.amount_df, 'd', ctx.meta) : null;
            let total = ctx.amount ? `{{ format_currency(total('${ctx.amount}')) }}` : null;
            let more = '{% if more %}…e mais {{ more }} — ver todas: {{ link }}{% endif %}';
            let list = `{% for d in docs %}• {{ d.name }}${title}\n{% endfor %}${more}`;
            let list_amount = `{% for d in docs %}• {{ d.name }}${title}${amount ? ' — ' + amount : ''}\n{% endfor %}${more}`;
            let header = '📋 *{{ report_name }}*{% if recipient_name %} — {{ recipient_name }}{% endif %} — {{ format_date(date) }}\n' +
                `{{ count }} registo(s)${total ? ' · total ' + total : ''}\n\n`;
            return [
                { label: __('Full message'), hint: __('Header, count, total and the list'), text: header + list_amount + '\n' },
                { label: __('List: ID — name'), text: list + '\n' },
                amount && { label: __('List with amount'), text: list_amount + '\n' },
                { label: __('Header + count'), text: header },
                total && { label: __('Total'), text: `Total: ${total}\n` },
                frm.doc.split_by_field && { label: __('Greeting (per person)'), text: 'Olá {{ recipient_name }}, estes são os seus pendentes:\n\n' },
                { label: __('Nothing pending'), hint: __('Only when nothing matches (turn off "Send only if data")'),
                    text: '{% if not count %}Nada pendente hoje 🎉{% endif %}\n' },
                { label: __('"…e mais N" + link'), hint: __('Opens the full list in ERPNext with the same filters'),
                    text: more + '\n' },
                { label: __('Link'), hint: __('List in ERPNext with the same filters'), text: '🔗 {{ link }}\n' },
                frm.doc.group_id && { label: __('Group tags'), text: '{{ mentions }}' },
            ];
        }
    });
}

// ─── Report ───────────────────────────────────────────────────────────────────

function setup_report_template_help(frm) {
    frappe.whatsapp.template_helper(frm, {
        field: 'message_template',
        doctype: null,
        mode: 'report',
        tag_keys: frm.doc.group_id ? () => frappe.whatsapp.tag_keys(frm, 'group_mentions') : null,
        variables: [
            ['{{ report_name }}', __('Name of the Frappe report')],
            ['{{ rows }}', __('Number of rows the report returned')],
            ['{{ summary }}', __('First rows as text (needs "Include Data Summary")')],
            ['{{ format_date(date) }}', __('Today\'s date')],
            ['{{ datetime }}', __('Date and time of the run')],
            ['{{ link }}', __('Link to the report in ERPNext with the same filters')],
            ['{{ filters }}', __('The filters used (e.g. filters.company)')],
            ['{{ mentions }}', __('Tags for group members')],
            ["{{ tag('supervisor') }}", __('Tag one person by role (set roles in Select Members to Tag)')],
        ],
        snippets: function () {
            let header = '📊 *{{ report_name }}* — {{ format_date(date) }}\n{{ rows }} registo(s)\n';
            let files = (frm.doc.include_excel || frm.doc.include_pdf) ? '\n📎 Ficheiro(s) em anexo\n' : '';
            return [
                { label: __('Full message'), hint: __('Header, row count, summary and link'),
                    text: header + '{% if summary %}\n{{ summary }}\n{% endif %}\n🔗 {{ link }}\n' + files },
                { label: __('Header + count'), text: header },
                { label: __('Summary'), hint: __('First rows as text (turn on "Include Data Summary")'),
                    text: '{{ summary }}\n' },
                { label: __('Nothing found'), hint: __('Only when the report is empty (turn off "Send only if data")'),
                    text: '{% if not rows %}Sem registos hoje 🎉{% endif %}\n' },
                { label: __('Link'), hint: __('Report in ERPNext with the same filters'), text: '🔗 {{ link }}\n' },
                frm.doc.group_id && { label: __('Group tags'), text: '{{ mentions }}' },
            ];
        }
    });
}

function describe_list_filters(frm) {
    if (frm.doc.source !== 'Document List') return;
    frappe.whatsapp.describe_filters(frm, { doctype: frm.doc.list_doctype, field: 'list_filters' });
}

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

function show_messages_preview(frm, method) {
    let is_report = method === 'preview_report';
    frm.call({
        method: method,
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
                        <span class="text-muted">${is_report ? __('{0} registo(s)', [m.count]) : __('{0} documento(s)', [m.count])}</span>
                        ${m.mention_everyone ? `<span class="indicator-pill blue">${__('Marca todos')}</span>` : ''}
                    </div>
                    <div style="background:#DCF8C6;padding:8px;border-radius:6px;white-space:pre-wrap;font-family:system-ui,sans-serif;">${frappe.whatsapp.render_tags(m.message || '', p.mention_names || {})}</div>
                </div>`).join('')
                : `<p class="text-muted">${is_report
                    ? __('Nada a enviar: o relatório não devolveu dados ("Enviar só se houver dados" está ativo).')
                    : __('Nada a enviar: nenhum documento corresponde aos filtros.')}</p>`;

            if (p.messages.length && p.attachments && p.attachments.length) {
                body += `<p class="small">📎 ${__('Anexos enviados com cada mensagem')}: ${esc(p.attachments.join(', '))}</p>`;
            }
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
