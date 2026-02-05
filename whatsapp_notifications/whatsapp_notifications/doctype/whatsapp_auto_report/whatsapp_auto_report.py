# Copyright (c) 2024, Entretech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate, get_datetime, add_days, get_first_day, get_last_day, today
import json


class WhatsAppAutoReport(Document):
    def validate(self):
        self.validate_filters()
        self.validate_schedule()

    def validate_filters(self):
        """Validate JSON filters"""
        if self.filters:
            try:
                json.loads(self.filters)
            except json.JSONDecodeError:
                frappe.throw(_("Filters must be valid JSON"))

    def validate_schedule(self):
        """Validate schedule configuration"""
        if self.frequency == "Weekly" and not self.day_of_week:
            frappe.throw(_("Day of Week is required for Weekly frequency"))

        if self.frequency in ("Monthly", "Quarterly") and not self.day_of_month:
            frappe.throw(_("Day of Month is required for Monthly/Quarterly frequency"))

        if self.day_of_month and (self.day_of_month < 1 or self.day_of_month > 28):
            frappe.throw(_("Day of Month must be between 1 and 28"))

    def get_filters(self):
        """Get report filters with dynamic date handling"""
        filters = {}

        # Parse static filters
        if self.filters:
            try:
                filters = json.loads(self.filters)
            except json.JSONDecodeError:
                pass

        # Apply dynamic date filters
        if self.dynamic_filters:
            date_filters = self.parse_dynamic_filters()
            filters.update(date_filters)

        return filters

    def parse_dynamic_filters(self):
        """Parse dynamic date filter expressions"""
        if not self.dynamic_filters:
            return {}

        filters = {}
        today_date = getdate(today())

        date_ranges = {
            "today": (today_date, today_date),
            "yesterday": (add_days(today_date, -1), add_days(today_date, -1)),
            "this_week": (add_days(today_date, -today_date.weekday()), today_date),
            "last_week": (add_days(today_date, -today_date.weekday() - 7), add_days(today_date, -today_date.weekday() - 1)),
            "this_month": (get_first_day(today_date), today_date),
            "last_month": (get_first_day(add_days(get_first_day(today_date), -1)), add_days(get_first_day(today_date), -1)),
            "this_quarter": self.get_quarter_dates(today_date, current=True),
            "last_quarter": self.get_quarter_dates(today_date, current=False),
            "this_year": (frappe.utils.get_first_day_of_year(today_date), today_date),
            "last_year": (frappe.utils.get_first_day_of_year(add_days(frappe.utils.get_first_day_of_year(today_date), -1)),
                         frappe.utils.get_last_day_of_year(add_days(frappe.utils.get_first_day_of_year(today_date), -1)))
        }

        # Parse expressions like "from_date:this_month, to_date:this_month"
        for expr in self.dynamic_filters.split(","):
            expr = expr.strip()
            if ":" in expr:
                field, period = expr.split(":", 1)
                field = field.strip()
                period = period.strip().lower()

                if period in date_ranges:
                    from_date, to_date = date_ranges[period]
                    if "from" in field.lower() or "start" in field.lower():
                        filters[field] = str(from_date)
                    elif "to" in field.lower() or "end" in field.lower():
                        filters[field] = str(to_date)
                    else:
                        # For single date fields, use from_date
                        filters[field] = str(from_date)

        return filters

    def get_quarter_dates(self, date, current=True):
        """Get quarter start and end dates"""
        month = date.month
        year = date.year

        if current:
            quarter = (month - 1) // 3 + 1
        else:
            quarter = (month - 1) // 3
            if quarter == 0:
                quarter = 4
                year -= 1

        quarter_start_month = (quarter - 1) * 3 + 1
        quarter_start = getdate("{}-{:02d}-01".format(year, quarter_start_month))
        quarter_end = get_last_day(add_days(quarter_start, 62))

        return (quarter_start, quarter_end)

    def should_send_today(self):
        """Check if report should be sent today"""
        today_date = getdate(today())
        now = now_datetime()

        if self.frequency == "Daily":
            return True

        elif self.frequency == "Weekly":
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            return day_names[today_date.weekday()] == self.day_of_week

        elif self.frequency == "Monthly":
            return today_date.day == self.day_of_month

        elif self.frequency == "Quarterly":
            # Send on day_of_month of Jan, Apr, Jul, Oct
            quarter_months = [1, 4, 7, 10]
            return today_date.month in quarter_months and today_date.day == self.day_of_month

        return False

    def is_time_to_send(self):
        """Check if it's time to send (within 30 min window)"""
        if not self.send_time:
            return False

        now = now_datetime()
        send_time = get_datetime("{} {}".format(today(), self.send_time))

        # Check if we're within 30 minutes after send_time
        diff_minutes = (now - send_time).total_seconds() / 60

        return 0 <= diff_minutes <= 30

    def was_sent_today(self):
        """Check if report was already sent today"""
        if not self.last_sent:
            return False

        return getdate(self.last_sent) == getdate(today())

    @frappe.whitelist()
    def generate_and_send(self):
        """Generate report and send via WhatsApp"""
        try:
            # Generate report data
            report_data = self.get_report_data()

            if not report_data and self.send_if_data:
                self.db_set("last_status", "Skipped - No data")
                return {"success": True, "skipped": True, "reason": "No data"}

            # Build message
            message = self.build_message(report_data)

            # Generate attachments
            attachments = []

            if self.include_excel:
                excel_data = self.generate_excel(report_data)
                if excel_data:
                    attachments.append({
                        "type": "excel",
                        "data": excel_data,
                        "filename": "{}.xlsx".format(self.report_name.replace(" ", "_"))
                    })

            if self.include_pdf:
                pdf_data = self.generate_pdf(report_data)
                if pdf_data:
                    attachments.append({
                        "type": "pdf",
                        "data": pdf_data,
                        "filename": "{}.pdf".format(self.report_name.replace(" ", "_"))
                    })

            # Send to all recipients
            recipients = self.get_recipients()
            sent_count = 0
            errors = []

            for phone in recipients:
                try:
                    if attachments:
                        # Send with attachment (use first attachment as primary)
                        result = send_report_with_attachment(
                            phone=phone,
                            message=message,
                            attachments=attachments,
                            report_name=self.report_name
                        )
                    else:
                        # Send text only
                        from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification
                        result = send_whatsapp_notification(
                            phone=phone,
                            message=message,
                            reference_doctype="WhatsApp Auto Report",
                            reference_name=self.name,
                            notification_rule=None,
                            recipient_name=None
                        )

                    if result.get("success") or result.get("queued"):
                        sent_count += 1
                    else:
                        errors.append("{}: {}".format(phone, result.get("error", "Unknown error")))

                except Exception as e:
                    errors.append("{}: {}".format(phone, str(e)))

            # Update status
            self.db_set("last_sent", now_datetime())

            if sent_count > 0:
                self.db_set("last_status", "Sent to {} recipients".format(sent_count))
                self.db_set("last_error", None)
            else:
                self.db_set("last_status", "Failed")
                self.db_set("last_error", "\n".join(errors[:5]))  # First 5 errors

            frappe.db.commit()

            return {
                "success": sent_count > 0,
                "sent": sent_count,
                "errors": errors
            }

        except Exception as e:
            self.db_set("last_status", "Error")
            self.db_set("last_error", str(e)[:500])
            frappe.db.commit()

            frappe.log_error(
                message="Error generating/sending report {}: {}".format(self.name, str(e)),
                title="WhatsApp Auto Report Error"
            )
            return {"success": False, "error": str(e)}

    def get_report_data(self):
        """Get report data"""
        filters = self.get_filters()

        # Set user context for permissions
        user = self.user or "Administrator"

        try:
            # Get report document
            report = frappe.get_doc("Report", self.report)

            if report.report_type == "Report Builder":
                # Report Builder reports
                result = frappe.get_list(
                    report.ref_doctype,
                    filters=filters,
                    fields=["*"],
                    limit=self.no_of_rows or 500,
                    as_list=False
                )
                columns = self.get_report_builder_columns(report)
                return {"columns": columns, "result": result}

            else:
                # Query Report or Script Report
                result = frappe.call(
                    "frappe.desk.query_report.run",
                    report_name=self.report,
                    filters=filters,
                    user=user
                )

                if result:
                    data = result.get("result", [])
                    if self.no_of_rows and len(data) > self.no_of_rows:
                        data = data[:self.no_of_rows]

                    return {
                        "columns": result.get("columns", []),
                        "result": data
                    }

        except Exception as e:
            frappe.log_error(
                message="Error getting report data for {}: {}".format(self.name, str(e)),
                title="WhatsApp Auto Report Data Error"
            )
            raise

        return None

    def get_report_builder_columns(self, report):
        """Get columns for Report Builder report"""
        if report.ref_doctype:
            meta = frappe.get_meta(report.ref_doctype)
            return [{"label": f.label, "fieldname": f.fieldname, "fieldtype": f.fieldtype}
                    for f in meta.fields if f.in_list_view]
        return []

    def get_recipients(self):
        """Get list of recipient phone numbers"""
        if not self.recipients:
            return []

        recipients = []
        for line in self.recipients.split("\n"):
            phone = line.strip()
            if phone:
                recipients.append(phone)

        return recipients

    def build_message(self, report_data):
        """Build the message to send"""
        context = {
            "report_name": self.report,
            "date": today(),
            "datetime": now_datetime().strftime("%Y-%m-%d %H:%M"),
            "rows": len(report_data.get("result", [])) if report_data else 0,
            "summary": "",
            "filters": self.get_filters()
        }

        # Build summary if enabled
        if self.include_summary and report_data:
            context["summary"] = self.build_summary(report_data)

        # Build report link if enabled
        if self.include_link:
            from urllib.parse import urlencode
            filters_str = urlencode(self.get_filters())
            context["link"] = "{}/app/query-report/{}?{}".format(
                frappe.utils.get_url(),
                self.report.replace(" ", "%20"),
                filters_str
            )

        # Render custom template or use default
        if self.message_template:
            message = frappe.render_template(self.message_template, context)
        else:
            message = self.get_default_message(context)

        return message

    def get_default_message(self, context):
        """Get default message template"""
        message = "📊 *Relatório: {}*\n".format(context["report_name"])
        message += "Data: {}\n\n".format(context["datetime"])

        if context["rows"] > 0:
            message += "Total de registros: {}\n".format(context["rows"])

            if context.get("summary"):
                message += "\n{}\n".format(context["summary"])
        else:
            message += "Nenhum dado encontrado para os filtros aplicados.\n"

        if context.get("link"):
            message += "\n🔗 Ver relatório completo:\n{}\n".format(context["link"])

        if self.include_excel or self.include_pdf:
            message += "\n📎 Arquivo(s) em anexo"

        return message

    def build_summary(self, report_data, max_rows=5):
        """Build text summary of report data"""
        if not report_data or not report_data.get("result"):
            return ""

        columns = report_data.get("columns", [])
        data = report_data.get("result", [])[:max_rows]

        if not columns or not data:
            return ""

        # Get column names
        col_names = []
        for col in columns[:5]:  # Max 5 columns in summary
            if isinstance(col, dict):
                col_names.append(col.get("label", col.get("fieldname", "")))
            else:
                col_names.append(str(col))

        summary_lines = []

        for row in data:
            if isinstance(row, dict):
                values = [str(row.get(col.get("fieldname", ""), ""))[:20] for col in columns[:5] if isinstance(col, dict)]
            elif isinstance(row, (list, tuple)):
                values = [str(v)[:20] for v in row[:5]]
            else:
                continue

            summary_lines.append(" | ".join(values))

        if len(report_data.get("result", [])) > max_rows:
            summary_lines.append("... e mais {} registros".format(len(report_data["result"]) - max_rows))

        return "\n".join(summary_lines)

    def generate_excel(self, report_data):
        """Generate Excel file from report data"""
        if not report_data or not report_data.get("result"):
            return None

        try:
            import io
            from frappe.utils.xlsxutils import make_xlsx

            columns = report_data.get("columns", [])
            data = report_data.get("result", [])

            # Format columns for xlsx
            xlsx_columns = []
            for col in columns:
                if isinstance(col, dict):
                    xlsx_columns.append(col.get("label", col.get("fieldname", "")))
                else:
                    xlsx_columns.append(str(col))

            # Format data rows
            xlsx_data = [xlsx_columns]  # Header row

            for row in data:
                if isinstance(row, dict):
                    row_data = []
                    for col in columns:
                        if isinstance(col, dict):
                            row_data.append(row.get(col.get("fieldname", ""), ""))
                        else:
                            row_data.append(row.get(col, ""))
                    xlsx_data.append(row_data)
                elif isinstance(row, (list, tuple)):
                    xlsx_data.append(list(row))

            xlsx_file = make_xlsx(xlsx_data, self.report)
            return xlsx_file.getvalue()

        except Exception as e:
            frappe.log_error(
                message="Error generating Excel for {}: {}".format(self.name, str(e)),
                title="WhatsApp Auto Report Excel Error"
            )
            return None

    def generate_pdf(self, report_data):
        """Generate PDF from report data"""
        if not report_data or not report_data.get("result"):
            return None

        try:
            # Build HTML for PDF
            html = self.build_pdf_html(report_data)

            # Generate PDF
            pdf = frappe.utils.pdf.get_pdf(html)
            return pdf

        except Exception as e:
            frappe.log_error(
                message="Error generating PDF for {}: {}".format(self.name, str(e)),
                title="WhatsApp Auto Report PDF Error"
            )
            return None

    def build_pdf_html(self, report_data):
        """Build HTML for PDF generation"""
        columns = report_data.get("columns", [])
        data = report_data.get("result", [])

        # Get column headers
        headers = []
        for col in columns:
            if isinstance(col, dict):
                headers.append(col.get("label", col.get("fieldname", "")))
            else:
                headers.append(str(col))

        html = """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; font-size: 10px; }
                h1 { font-size: 16px; margin-bottom: 10px; }
                .meta { color: #666; margin-bottom: 20px; }
                table { width: 100%; border-collapse: collapse; }
                th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
                th { background-color: #f5f5f5; font-weight: bold; }
                tr:nth-child(even) { background-color: #fafafa; }
            </style>
        </head>
        <body>
            <h1>{report_name}</h1>
            <div class="meta">
                Gerado em: {datetime}<br>
                Total de registros: {rows}
            </div>
            <table>
                <thead>
                    <tr>
                        {headers}
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </body>
        </html>
        """.format(
            report_name=self.report,
            datetime=now_datetime().strftime("%Y-%m-%d %H:%M"),
            rows=len(data),
            headers="".join(["<th>{}</th>".format(h) for h in headers]),
            rows_html=self.build_table_rows(columns, data)
        )

        return html

    def build_table_rows(self, columns, data):
        """Build HTML table rows"""
        rows_html = []

        for row in data:
            cells = []
            if isinstance(row, dict):
                for col in columns:
                    if isinstance(col, dict):
                        value = row.get(col.get("fieldname", ""), "")
                    else:
                        value = row.get(col, "")
                    cells.append("<td>{}</td>".format(frappe.utils.escape_html(str(value) if value else "")))
            elif isinstance(row, (list, tuple)):
                for value in row:
                    cells.append("<td>{}</td>".format(frappe.utils.escape_html(str(value) if value else "")))

            rows_html.append("<tr>{}</tr>".format("".join(cells)))

        return "".join(rows_html)


def send_report_with_attachment(phone, message, attachments, report_name):
    """Send report with attachment via WhatsApp"""
    import base64
    from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
    from whatsapp_notifications.whatsapp_notifications.utils import format_phone_number
    from whatsapp_notifications.whatsapp_notifications.api import make_http_request

    settings = get_settings()

    if not settings.get("enabled"):
        return {"success": False, "error": "WhatsApp notifications disabled"}

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return {"success": False, "error": "Invalid phone number"}

    results = []

    # Send text message first
    try:
        url = "{}/message/sendText/{}".format(
            settings.get("api_url"),
            settings.get("instance_name")
        )

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "apikey": settings.get("api_key")
        }

        payload = {
            "number": formatted_phone,
            "text": message
        }

        response = make_http_request(url, method="POST", headers=headers, data=payload)
        results.append({"type": "text", "success": True})

    except Exception as e:
        results.append({"type": "text", "success": False, "error": str(e)})

    # Send attachments
    for attachment in attachments:
        try:
            media_base64 = base64.b64encode(attachment["data"]).decode("utf-8")

            if attachment["type"] == "excel":
                mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif attachment["type"] == "pdf":
                mimetype = "application/pdf"
            else:
                mimetype = "application/octet-stream"

            url = "{}/message/sendMedia/{}".format(
                settings.get("api_url"),
                settings.get("instance_name")
            )

            payload = {
                "number": formatted_phone,
                "mediatype": "document",
                "mimetype": mimetype,
                "caption": "",
                "media": media_base64,
                "fileName": attachment["filename"]
            }

            response = make_http_request(url, method="POST", headers=headers, data=payload)
            results.append({"type": attachment["type"], "success": True})

        except Exception as e:
            results.append({"type": attachment["type"], "success": False, "error": str(e)})

    # Return success if at least text was sent
    success = any(r.get("success") for r in results)
    return {"success": success, "results": results}


def process_auto_reports():
    """Process all due auto reports - called by scheduler"""
    reports = frappe.get_all(
        "WhatsApp Auto Report",
        filters={"enabled": 1},
        pluck="name"
    )

    for report_name in reports:
        try:
            report = frappe.get_doc("WhatsApp Auto Report", report_name)

            # Check if should send today and at this time
            if report.should_send_today() and report.is_time_to_send() and not report.was_sent_today():
                frappe.enqueue(
                    "whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_auto_report.whatsapp_auto_report.send_auto_report",
                    report_name=report_name,
                    queue="long"
                )

        except Exception as e:
            frappe.log_error(
                message="Error checking auto report {}: {}".format(report_name, str(e)),
                title="WhatsApp Auto Report Scheduler Error"
            )


def send_auto_report(report_name):
    """Send a specific auto report"""
    report = frappe.get_doc("WhatsApp Auto Report", report_name)
    return report.generate_and_send()
