# Copyright (c) 2024, Entretech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppApprovalTemplate(Document):
    def validate(self):
        self.validate_options()
        self.validate_workflow_state()

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

    def validate_workflow_state(self):
        """Validate workflow state if specified"""
        if self.workflow_state and self.document_type:
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

        # Append response options
        message += "\n\n"
        message += _("Please respond with:") + "\n"

        for option in sorted(self.response_options, key=lambda x: x.option_number):
            message += "{} - {}\n".format(option.option_number, option.option_label)

        message += "\n" + _("Reply with the number of your choice.")

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


def get_template_for_workflow_state(doctype, workflow_state):
    """
    Get approval template triggered by a workflow state

    Args:
        doctype: Document type
        workflow_state: Workflow state name

    Returns:
        WhatsApp Approval Template or None
    """
    templates = frappe.get_all(
        "WhatsApp Approval Template",
        filters={
            "enabled": 1,
            "document_type": doctype,
            "workflow_state": workflow_state
        },
        limit=1
    )

    if templates:
        return frappe.get_doc("WhatsApp Approval Template", templates[0].name)

    return None
