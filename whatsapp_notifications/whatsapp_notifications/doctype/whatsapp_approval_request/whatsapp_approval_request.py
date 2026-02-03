# Copyright (c) 2024, Entretech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class WhatsAppApprovalRequest(Document):
    def before_insert(self):
        if not self.sent_at:
            self.sent_at = now_datetime()

        if not self.expires_at and self.approval_template:
            template = frappe.get_doc("WhatsApp Approval Template", self.approval_template)
            expiry_hours = template.expiry_hours or 24
            self.expires_at = frappe.utils.add_to_date(
                self.sent_at,
                hours=expiry_hours
            )

    def is_expired(self):
        """Check if the request has expired"""
        if self.status != "Pending":
            return False

        if self.expires_at and now_datetime() > self.expires_at:
            return True

        return False

    def mark_expired(self):
        """Mark the request as expired"""
        self.db_set("status", "Expired")

    def mark_cancelled(self, reason=None):
        """Mark the request as cancelled"""
        self.db_set("status", "Cancelled")
        if reason:
            self.db_set("error_message", reason)

    def mark_error(self, error_message):
        """Mark the request as having an error"""
        self.db_set("status", "Error")
        self.db_set("error_message", error_message)

    def record_response(self, option_number, response_text, response_from):
        """
        Record a response to this approval request

        Args:
            option_number: The option number selected
            response_text: Raw response text
            response_from: Phone number that responded
        """
        self.db_set("response_option", option_number)
        self.db_set("response_text", response_text)
        self.db_set("response_from", response_from)
        self.db_set("responded_at", now_datetime())

    def mark_processed(self, action_description, new_status="Approved"):
        """
        Mark the request as processed

        Args:
            action_description: Description of the action executed
            new_status: New status (Approved/Rejected based on action)
        """
        self.db_set("processed", 1)
        self.db_set("action_executed", action_description)
        self.db_set("status", new_status)


def get_pending_request_by_phone(formatted_phone):
    """
    Find a pending approval request for a phone number

    Args:
        formatted_phone: Formatted phone number to match

    Returns:
        WhatsApp Approval Request or None
    """
    requests = frappe.get_all(
        "WhatsApp Approval Request",
        filters={
            "status": "Pending",
            "formatted_phone": formatted_phone
        },
        order_by="creation desc",
        limit=1
    )

    if requests:
        return frappe.get_doc("WhatsApp Approval Request", requests[0].name)

    return None


def get_pending_requests_for_document(doctype, docname):
    """
    Get all pending approval requests for a document

    Args:
        doctype: Document type
        docname: Document name

    Returns:
        list: List of WhatsApp Approval Request documents
    """
    requests = frappe.get_all(
        "WhatsApp Approval Request",
        filters={
            "status": "Pending",
            "reference_doctype": doctype,
            "reference_name": docname
        },
        order_by="creation desc"
    )

    return [frappe.get_doc("WhatsApp Approval Request", r.name) for r in requests]


def cancel_pending_requests_for_document(doctype, docname, reason=None):
    """
    Cancel all pending approval requests for a document

    Args:
        doctype: Document type
        docname: Document name
        reason: Optional reason for cancellation
    """
    requests = get_pending_requests_for_document(doctype, docname)

    for request in requests:
        request.mark_cancelled(reason or "Superseded by new request")
