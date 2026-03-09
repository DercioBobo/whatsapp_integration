frappe.pages['whatsapp-schedule-monitor'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('WhatsApp Schedule Monitor'),
        single_column: true
    });

    new WhatsAppScheduleMonitor(page, wrapper);
};

// ─── Main Controller ──────────────────────────────────────────────────────────

var WhatsAppScheduleMonitor = class WhatsAppScheduleMonitor {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.$body = $(wrapper).find('.page-content');
        this.data = null;

        this.from_date = frappe.datetime.nowdate();
        this.to_date = frappe.datetime.add_days(frappe.datetime.nowdate(), 30);
        this.rule_filter = '';
        this.status_filter = '';

        this.setup_toolbar();
        this.render_skeleton();
        this.load_data();
    }

    // ── Toolbar ──────────────────────────────────────────────────────────────

    setup_toolbar() {
        var me = this;

        // Date range
        this.page.add_field({
            fieldname: 'from_date',
            label: __('From'),
            fieldtype: 'Date',
            default: this.from_date,
            change() {
                me.from_date = this.get_value();
                me.load_data();
            }
        });

        this.page.add_field({
            fieldname: 'to_date',
            label: __('To'),
            fieldtype: 'Date',
            default: this.to_date,
            change() {
                me.to_date = this.get_value();
                me.load_data();
            }
        });

        // Rule filter
        this.page.add_field({
            fieldname: 'rule_filter',
            label: __('Rule'),
            fieldtype: 'Link',
            options: 'WhatsApp Notification Rule',
            change() {
                me.rule_filter = this.get_value();
                me.load_data();
            }
        });

        // Status filter
        this.page.add_field({
            fieldname: 'status_filter',
            label: __('Status'),
            fieldtype: 'Select',
            options: '\nToday\nUpcoming\nQueued\nSent\nOverdue\nFailed',
            change() {
                me.status_filter = this.get_value();
                me.render_entries();
            }
        });

        // Buttons
        this.page.set_primary_action(__('Refresh'), () => this.load_data(), 'refresh');

        this.page.add_menu_item(__('Run Scheduled Rules Now'), () => {
            frappe.confirm(
                __('Process all Days Before/After rules for today now?'),
                () => {
                    frappe.call({
                        method: 'whatsapp_notifications.whatsapp_notifications.tasks.trigger_scheduled_rules',
                        callback(r) {
                            frappe.show_alert({ message: __('Scheduled rules triggered'), indicator: 'green' }, 4);
                        }
                    });
                }
            );
        });
    }

    // ── Skeleton / Loading ────────────────────────────────────────────────────

    render_skeleton() {
        this.$body.html(`
            <div class="wsm-container" style="padding: 16px 0;">
                <div class="wsm-summary" style="margin-bottom: 20px;"></div>
                <div class="wsm-rules-section" style="margin-bottom: 24px;"></div>
                <div class="wsm-entries-section"></div>
            </div>
        `);
        this.$summary = this.$body.find('.wsm-summary');
        this.$rules = this.$body.find('.wsm-rules-section');
        this.$entries = this.$body.find('.wsm-entries-section');
    }

    // ── Data Loading ──────────────────────────────────────────────────────────

    load_data() {
        var me = this;
        this.$body.find('.wsm-container').css('opacity', '0.5');

        frappe.call({
            method: 'whatsapp_notifications.whatsapp_notifications.tasks.get_schedule_monitor_data',
            args: {
                from_date: this.from_date,
                to_date: this.to_date,
                rule_name: this.rule_filter || null
            },
            callback(r) {
                me.$body.find('.wsm-container').css('opacity', '1');
                if (r.message) {
                    me.data = r.message;
                    me.render_summary();
                    me.render_rules();
                    me.render_entries();
                }
            },
            error() {
                me.$body.find('.wsm-container').css('opacity', '1');
                frappe.show_alert({ message: __('Failed to load schedule data'), indicator: 'red' }, 5);
            }
        });
    }

    // ── Summary Cards ─────────────────────────────────────────────────────────

    render_summary() {
        var s = this.data.summary;
        var today = this.data.today;

        var cards = [
            { label: __('Today'), value: s.today, color: s.today > 0 ? '#f59e0b' : '#10b981', icon: '📅' },
            { label: __('Upcoming'), value: s.upcoming, color: '#3b82f6', icon: '⏳' },
            { label: __('Queued'), value: s.queued, color: '#8b5cf6', icon: '🔄' },
            { label: __('Sent'), value: s.sent, color: '#10b981', icon: '✅' },
            { label: __('Overdue'), value: s.overdue, color: s.overdue > 0 ? '#ef4444' : '#6b7280', icon: '⚠️' },
            { label: __('Failed'), value: s.failed, color: s.failed > 0 ? '#ef4444' : '#6b7280', icon: '❌' },
        ];

        var html = `
            <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch;">
                ${cards.map(c => `
                    <div style="
                        background:#fff;border:1px solid #e5e7eb;border-radius:8px;
                        padding:14px 20px;min-width:110px;flex:1;
                        border-left:4px solid ${c.color};
                        box-shadow:0 1px 3px rgba(0,0,0,.06);
                    ">
                        <div style="font-size:1.6em;line-height:1;">${c.icon} <span style="font-size:.7em;color:${c.color};font-weight:700;">${c.value}</span></div>
                        <div style="font-size:.78em;color:#6b7280;margin-top:4px;">${c.label}</div>
                    </div>
                `).join('')}
                <div style="
                    background:#fff;border:1px solid #e5e7eb;border-radius:8px;
                    padding:14px 20px;min-width:140px;flex:1;
                    border-left:4px solid #6b7280;
                    box-shadow:0 1px 3px rgba(0,0,0,.06);
                ">
                    <div style="font-size:.85em;font-weight:600;color:#374151;">📆 ${frappe.datetime.str_to_user(today)}</div>
                    <div style="font-size:.78em;color:#6b7280;margin-top:2px;">${__('Today')} &bull; ${__('Range')}: ${frappe.datetime.str_to_user(this.from_date)} → ${frappe.datetime.str_to_user(this.to_date)}</div>
                    <div style="font-size:.78em;color:#6b7280;">${s.total} ${__('documents total')}</div>
                </div>
            </div>
        `;
        this.$summary.html(html);
    }

    // ── Rules Section ─────────────────────────────────────────────────────────

    render_rules() {
        var rules = this.data.rules;
        if (!rules || rules.length === 0) {
            this.$rules.html(`
                <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:16px;color:#92400e;">
                    <strong>⚠ ${__('No scheduled rules found.')}</strong>
                    ${__('Create a WhatsApp Notification Rule with event "Days Before" or "Days After" to get started.')}
                </div>
            `);
            return;
        }

        var rows = rules.map(r => {
            var event_badge = r.event === 'Days Before'
                ? `<span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:10px;font-size:.75em;">${r.event}</span>`
                : r.event === 'Days After'
                ? `<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:10px;font-size:.75em;">${r.event}</span>`
                : `<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:.75em;">${r.event}</span>`;
            var time_desc = r.event === 'Days Before'
                ? __(`{0} days before {1}`, [r.days_offset, r.date_field])
                : r.event === 'Days After'
                ? __(`{0} days after {1}`, [r.days_offset, r.date_field])
                : __(`on the same day as {0}`, [r.date_field]);
            var sched_time = r.event === 'Days Before'
                ? `⏰ ${__('Fires at configured hour')} — ${__('sends when')} ${r.date_field} = today + ${r.days_offset}d`
                : r.event === 'Days After'
                ? `⏰ ${__('Fires at configured hour')} — ${__('sends when')} ${r.date_field} = today - ${r.days_offset}d`
                : `⏰ ${__('Fires at configured hour')} — ${__('sends when')} ${r.date_field} = today`;

            return `
                <tr>
                    <td style="font-weight:600;">
                        <a href="/app/whatsapp-notification-rule/${encodeURIComponent(r.name)}" target="_blank">
                            ${frappe.utils.escape_html(r.rule_name || r.name)}
                        </a>
                    </td>
                    <td>${frappe.utils.escape_html(r.document_type)}</td>
                    <td>${event_badge}</td>
                    <td>${frappe.utils.escape_html(r.date_field)} ± ${r.days_offset}d</td>
                    <td style="color:#6b7280;font-size:.82em;">${time_desc}</td>
                    <td style="color:#6b7280;font-size:.78em;">${sched_time}</td>
                    <td>
                        <span style="
                            background:${r.enabled ? '#dcfce7' : '#fee2e2'};
                            color:${r.enabled ? '#166534' : '#991b1b'};
                            padding:2px 8px;border-radius:10px;font-size:.75em;
                        ">${r.enabled ? __('Active') : __('Inactive')}</span>
                    </td>
                </tr>
            `;
        }).join('');

        this.$rules.html(`
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);">
                <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center;">
                    <strong style="font-size:.9em;">📋 ${__('Active Scheduled Rules')} (${rules.length})</strong>
                </div>
                <div style="overflow-x:auto;">
                    <table class="table table-condensed" style="margin:0;font-size:.85em;">
                        <thead style="background:#f9fafb;">
                            <tr>
                                <th>${__('Rule')}</th>
                                <th>${__('Document Type')}</th>
                                <th>${__('Event')}</th>
                                <th>${__('Field / Offset')}</th>
                                <th>${__('Trigger Logic')}</th>
                                <th>${__('Scheduler')}</th>
                                <th>${__('Status')}</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        `);
    }

    // ── Entries Table ─────────────────────────────────────────────────────────

    render_entries() {
        if (!this.data) return;

        var entries = this.data.entries;

        // Apply status filter
        if (this.status_filter) {
            entries = entries.filter(e => e.status === this.status_filter);
        }

        if (entries.length === 0) {
            this.$entries.html(`
                <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:32px;text-align:center;color:#6b7280;">
                    ${__('No scheduled notifications found for the selected period and filters.')}
                </div>
            `);
            return;
        }

        var today = this.data.today;
        var rows = entries.map(e => this.render_entry_row(e, today)).join('');

        this.$entries.html(`
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);">
                <div style="padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center;">
                    <strong style="font-size:.9em;">🗓 ${__('Notification Schedule')} (${entries.length})</strong>
                    <span style="font-size:.78em;color:#6b7280;">${__('Sorted by notification date')}</span>
                </div>
                <div style="overflow-x:auto;">
                    <table class="table table-condensed table-hover" style="margin:0;font-size:.84em;">
                        <thead style="background:#f9fafb;">
                            <tr>
                                <th>${__('Notification Date')}</th>
                                <th>${__('Document')}</th>
                                <th>${__('Document Type')}</th>
                                <th>${__('Rule')}</th>
                                <th>${__('Event')}</th>
                                <th>${__('Document Date')}</th>
                                <th>${__('Status')}</th>
                                <th>${__('Sent At')}</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        `);
    }

    render_entry_row(e, today) {
        var status_cfg = this.status_config(e.status);
        var is_today = e.notification_date === today;

        var notif_date_html = is_today
            ? `<strong style="color:#f59e0b;">📅 ${frappe.datetime.str_to_user(e.notification_date)} (${__('Today')})</strong>`
            : frappe.datetime.str_to_user(e.notification_date);

        var event_label = e.event === 'Days Before'
            ? `${e.days_offset}d ${__('before')} ${e.date_field}`
            : e.event === 'Days After'
            ? `${e.days_offset}d ${__('after')} ${e.date_field}`
            : __('same day as {0}', [e.date_field]);

        var doc_link = `<a href="/app/${frappe.router.slug(e.document_type)}/${encodeURIComponent(e.document_name)}" target="_blank">
            ${frappe.utils.escape_html(e.document_name)}
        </a>`;

        return `
            <tr style="${is_today ? 'background:#fffbeb;' : ''}">
                <td>${notif_date_html}</td>
                <td>${doc_link}</td>
                <td style="color:#6b7280;">${frappe.utils.escape_html(e.document_type)}</td>
                <td>
                    <a href="/app/whatsapp-notification-rule/${encodeURIComponent(e.rule)}" target="_blank">
                        ${frappe.utils.escape_html(e.rule_label)}
                    </a>
                </td>
                <td style="font-size:.8em;color:#6b7280;">${frappe.utils.escape_html(event_label)}</td>
                <td style="color:#6b7280;">${frappe.datetime.str_to_user(e.doc_date)}</td>
                <td>
                    <span style="
                        background:${status_cfg.bg};color:${status_cfg.fg};
                        padding:2px 9px;border-radius:10px;font-size:.75em;font-weight:600;
                    ">${status_cfg.icon} ${__(e.status)}</span>
                </td>
                <td style="color:#6b7280;font-size:.8em;">
                    ${e.sent_at ? frappe.datetime.str_to_user(e.sent_at) : '—'}
                </td>
            </tr>
        `;
    }

    status_config(status) {
        const map = {
            'Today':    { bg: '#fef3c7', fg: '#92400e', icon: '📅' },
            'Upcoming': { bg: '#dbeafe', fg: '#1d4ed8', icon: '⏳' },
            'Queued':   { bg: '#ede9fe', fg: '#6d28d9', icon: '🔄' },
            'Sent':     { bg: '#dcfce7', fg: '#166534', icon: '✅' },
            'Overdue':  { bg: '#fee2e2', fg: '#991b1b', icon: '⚠️' },
            'Failed':   { bg: '#fee2e2', fg: '#991b1b', icon: '❌' },
            'Cancelled':{ bg: '#f3f4f6', fg: '#6b7280', icon: '🚫' },
        };
        return map[status] || { bg: '#f3f4f6', fg: '#6b7280', icon: '•' };
    }
};
