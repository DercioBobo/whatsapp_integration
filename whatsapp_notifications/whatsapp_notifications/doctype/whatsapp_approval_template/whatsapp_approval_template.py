# Copyright (c) 2024, Entretech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppApprovalTemplate(Document):
    def validate(self):
        self.validate_options()
        self.validate_recipients()
        self.validate_trigger()

    def validate_options(self):
        """Ensure option numbers are unique and sequential"""
        if not self.response_options:
            frappe.throw(_("At least one response option is required"))

        option_numbers = [opt.option_number for opt in self.response_options]

        # Check for duplicates
        if len(option_numbers) != len(set(option_numbers)):
            frappe.throw(_("Option numbers must be unique"))

        # Check for positive numbers
        for num in option_numbers:
            if num < 1:
                frappe.throw(_("Option numbers must be positive integers"))

    def validate_recipients(self):
        """Validate recipient configuration"""
        if self.recipient_type in ("Field Value", "Both") and not self.phone_field:
            frappe.throw(_("Phone Field is required when Recipient Type is '{0}'").format(self.recipient_type))

        if self.recipient_type in ("Fixed Numbers", "Both") and not self.fixed_recipients:
            frappe.throw(_("Fixed Recipients is required when Recipient Type is '{0}'").format(self.recipient_type))

    def validate_trigger(self):
        """Validate trigger configuration"""
        if self.event == "Workflow State Change" and not self.workflow_state:
            frappe.throw(_("Workflow State is required when Event is 'Workflow State Change'"))

        if self.event == "Workflow State Change" and self.document_type:
            # Check if document type has a workflow
            workflow = frappe.get_all(
                "Workflow",
                filters={"document_type": self.document_type, "is_active": 1},
                limit=1
            )

            if not workflow:
                frappe.msgprint(
                    _("Note: No active workflow found for {0}. The workflow state trigger will not work.").format(
                        self.document_type
                    ),
                    indicator="orange"
                )

    def get_recipients(self, doc):
        """
        Get list of recipient phone numbers

        Args:
            doc: The document

        Returns:
            list: List of phone numbers
        """
        recipients = []

        # Get from document field
        if self.recipient_type in ("Field Value", "Both") and self.phone_field:
            phone = get_phone_from_document(doc, self.phone_field)
            if phone:
                recipients.append(phone)

        # Get fixed recipients
        if self.recipient_type in ("Fixed Numbers", "Both") and self.fixed_recipients:
            # Parse fixed recipients (comma or newline separated)
            fixed = self.fixed_recipients.replace(",", "\n")
            for line in fixed.split("\n"):
                phone = line.strip()
                if phone and phone not in recipients:
                    recipients.append(phone)

        return recipients

    def render_message(self, doc):
        """
        Render the approval message for a document

        Args:
            doc: The document to render the message for

        Returns:
            str: Rendered message with options appended
        """
        from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_template_context

        context = get_template_context(doc)

        # Render main message
        message = frappe.render_template(self.message_template, context)

        # Append response options with customizable text
        message += "\n\n"

        # Header text (customizable)
        header_text = self.options_header_text or _("Please respond with:")
        message += header_text + "\n"

        for option in sorted(self.response_options, key=lambda x: x.option_number):
            message += "{} - {}\n".format(option.option_number, option.option_label)

        # Footer text (customizable)
        footer_text = self.options_footer_text or _("Reply with the number of your choice.")
        message += "\n" + footer_text

        return message

    def render_confirmation(self, doc, option_label, action_result=None):
        """
        Render the confirmation message

        Args:
            doc: The document
            option_label: The selected option label
            action_result: Result of the action (if any)

        Returns:
            str: Rendered confirmation message
        """
        if not self.send_confirmation:
            return None

        if not self.confirmation_template:
            # Default confirmation
            return _("Thank you! {0} has been {1}.").format(doc.name, option_label)

        from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_template_context

        context = get_template_context(doc)
        context["option_label"] = option_label
        context["action_result"] = action_result

        return frappe.render_template(self.confirmation_template, context)

    def render_invalid_response_message(self, received_text):
        """
        Render the invalid response help message

        Args:
            received_text: The invalid text received

        Returns:
            str: Help message or None
        """
        if not self.send_invalid_response_help:
            return None

        # Build options list for context
        options = []
        for option in sorted(self.response_options, key=lambda x: x.option_number):
            options.append({
                "number": option.option_number,
                "label": option.option_label
            })

        if self.invalid_response_template:
            context = {
                "received_text": received_text[:50] if received_text else "",
                "options": options
            }
            return frappe.render_template(self.invalid_response_template, context)

        # Default message
        message = _("Sorry, I didn't understand your response: '{0}'").format(received_text[:50] if received_text else "")
        message += "\n\n"
        message += (self.options_header_text or _("Please respond with:")) + "\n"

        for option in options:
            message += "{} - {}\n".format(option["number"], option["label"])

        message += "\n" + _("Reply with just the number.")

        return message

    def get_option_by_number(self, option_number):
        """
        Get an option by its number

        Args:
            option_number: The option number

        Returns:
            WhatsApp Approval Option or None
        """
        for option in self.response_options:
            if option.option_number == option_number:
                return option
        return None

    def check_condition(self, doc):
        """
        Check if the condition is met for this document

        Args:
            doc: The document to check

        Returns:
            bool: True if condition is met or no condition set
        """
        if not self.condition:
            return True

        try:
            from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_template_context
            context = get_template_context(doc)
            result = frappe.render_template(self.condition, context)

            # Handle various truthy values
            result = result.strip().lower()
            return result in ("true", "1", "yes")

        except Exception as e:
            frappe.log_error(
                "Error evaluating approval condition for {}: {}".format(self.name, str(e)),
                "WhatsApp Approval Condition Error"
            )
            return False


def get_phone_from_document(doc, phone_field):
    """
    Get phone number from document using field path

    Args:
        doc: Document
        phone_field: Field path (can use dot notation for linked docs)

    Returns:
        str: Phone number or None
    """
    if not phone_field:
        return None

    try:
        # Handle dot notation (e.g., "customer.mobile_no")
        if "." in phone_field:
            parts = phone_field.split(".")
            value = doc

            for i, part in enumerate(parts):
                if i == 0:
                    # First part is a field on the document
                    value = getattr(value, part, None)
                else:
                    # Subsequent parts need to fetch from linked doc
                    if value and i == 1:
                        # Get the linked doctype from meta
                        prev_field = parts[i - 1]
                        meta = frappe.get_meta(doc.doctype)
                        field_meta = meta.get_field(prev_field)

                        if field_meta and field_meta.fieldtype == "Link":
                            linked_doctype = field_meta.options
                            value = frappe.db.get_value(linked_doctype, value, part)
                        else:
                            return None
                    else:
                        return None

                if not value:
                    return None

            return value
        else:
            return getattr(doc, phone_field, None)
    except Exception:
        return None


def get_template_for_workflow_state(doctype, workflow_state):
    """
    Get approval template triggered by a workflow state

    Args:
        doctype: Document type
        workflow_state: Workflow state name

    Returns:
        WhatsApp Approval Template or None
    """
    try:
        templates = frappe.get_all(
            "WhatsApp Approval Template",
            filters={
                "enabled": 1,
                "document_type": doctype,
                "event": "Workflow State Change",
                "workflow_state": workflow_state
            },
            limit=1
        )

        if templates:
            return frappe.get_doc("WhatsApp Approval Template", templates[0].name)

        return None
    except Exception:
        # Column might not exist during migration
        return None


def get_templates_for_event(doctype, event):
    """
    Get approval templates triggered by an event

    Args:
        doctype: Document type
        event: Event name (After Insert, On Update, On Submit, On Cancel)

    Returns:
        list: List of WhatsApp Approval Template documents
    """
    try:
        # Check if table exists and has the event column
        if not frappe.db.table_exists("WhatsApp Approval Template"):
            return []

        templates = frappe.get_all(
            "WhatsApp Approval Template",
            filters={
                "enabled": 1,
                "document_type": doctype,
                "event": event
            }
        )

        return [frappe.get_doc("WhatsApp Approval Template", t.name) for t in templates]
    except Exception as e:
        # Log the error for debugging if debug mode is on
        from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
        try:
            settings = get_settings()
            if settings.get("enable_debug_logging"):
                frappe.log_error(
                    message="Error: {}".format(str(e)),
                    title="get_templates_for_event error"
                )
        except Exception:
            pass
        return []
