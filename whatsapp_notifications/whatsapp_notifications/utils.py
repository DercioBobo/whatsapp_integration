"""
WhatsApp Notifications - Utility Functions
Phone formatting, validation, and Jinja helpers
"""
import frappe
from frappe import _
import re


def format_phone_number(phone, country_code=None, local_length=None, local_prefixes=None):
    """
    Format phone number for WhatsApp API
    
    Args:
        phone: Raw phone number
        country_code: Country code to prepend (default from settings)
        local_length: Expected local number length (default from settings)
        local_prefixes: Valid local prefixes (default from settings)
    
    Returns:
        str: Formatted phone number or None if invalid
    
    Examples:
        format_phone_number("84 123 4567")  # Returns "258841234567"
        format_phone_number("+258841234567")  # Returns "258841234567"
        format_phone_number("258841234567")  # Returns "258841234567"
    """
    if not phone:
        return None
    
    # Convert to string and clean
    phone = str(phone).strip()
    
    # Remove common formatting characters
    phone = re.sub(r'[\s\-\.\(\)\+]', '', phone)
    
    # Remove any non-digit characters
    phone = re.sub(r'[^\d]', '', phone)
    
    if not phone:
        return None
    
    # Get settings if not provided
    if not country_code or not local_length or not local_prefixes:
        from whatsapp_notifications.whatsapp_notifications.doctype.evolution_api_settings.evolution_api_settings import get_settings
        settings = get_settings()
        
        country_code = country_code or settings.get("default_country_code", "258")
        local_length = local_length or settings.get("local_number_length", 9)
        local_prefixes = local_prefixes or settings.get("local_number_prefixes", [])
    
    # Ensure prefixes is a list
    if isinstance(local_prefixes, str):
        local_prefixes = [p.strip() for p in local_prefixes.split(",") if p.strip()]
    
    # Check if it's a local number that needs country code
    if len(phone) == local_length:
        # Check if starts with valid local prefix
        is_local = False
        for prefix in local_prefixes:
            if phone.startswith(prefix):
                is_local = True
                break
        
        # If no prefixes defined, assume it's local
        if not local_prefixes:
            is_local = True
        
        if is_local:
            phone = country_code + phone
    
    # Validate final length (should be at least country code + local length)
    min_length = len(country_code) + local_length - 1
    if len(phone) < min_length:
        return None
    
    return phone


def validate_phone_number(phone, country_code=None, local_length=None, local_prefixes=None):
    """
    Validate a phone number
    
    Args:
        phone: Phone number to validate
        country_code: Expected country code
        local_length: Expected local number length
        local_prefixes: Valid local prefixes
    
    Returns:
        tuple: (is_valid, formatted_number, error_message)
    """
    if not phone:
        return (False, None, _("Phone number is required"))
    
    formatted = format_phone_number(phone, country_code, local_length, local_prefixes)
    
    if not formatted:
        return (False, None, _("Invalid phone number format"))
    
    return (True, formatted, None)


def escape_json_string(text):
    """
    Escape a string for safe inclusion in JSON
    V13 sandbox compatible (no json module)
    
    Args:
        text: String to escape
    
    Returns:
        str: Escaped string
    """
    if not text:
        return ""
    
    # Escape in order: backslash, quotes, newlines, tabs, carriage returns
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "\\r")
    text = text.replace("\t", "\\t")
    
    return text


def strip_accents(text):
    """
    Remove Portuguese accents from text
    Useful for v13 sandbox where encoding can be problematic
    
    Args:
        text: Text with accents
    
    Returns:
        str: Text without accents
    """
    if not text:
        return text
    
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n',
        'Á': 'A', 'À': 'A', 'Ã': 'A', 'Â': 'A', 'Ä': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'Ó': 'O', 'Ò': 'O', 'Õ': 'O', 'Ô': 'O', 'Ö': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ç': 'C', 'Ñ': 'N'
    }
    
    for accented, plain in replacements.items():
        text = text.replace(accented, plain)
    
    return text


# ============================================================
# Jinja Template Helpers
# ============================================================

def jinja_methods():
    """
    Returns custom Jinja methods for use in templates
    """
    return {
        "format_phone": format_phone_number,
        "whatsapp_bold": whatsapp_bold,
        "whatsapp_italic": whatsapp_italic,
        "whatsapp_strike": whatsapp_strike,
        "whatsapp_code": whatsapp_code,
        "format_mzn": format_mzn,
        "strip_accents": strip_accents
    }


def whatsapp_bold(text):
    """Format text as bold for WhatsApp"""
    return "*{}*".format(text) if text else ""


def whatsapp_italic(text):
    """Format text as italic for WhatsApp"""
    return "_{}".format(text) if text else ""


def whatsapp_strike(text):
    """Format text as strikethrough for WhatsApp"""
    return "~{}~".format(text) if text else ""


def whatsapp_code(text):
    """Format text as monospace for WhatsApp"""
    return "`{}`".format(text) if text else ""


def format_mzn(amount, symbol="MZN"):
    """
    Format amount as Mozambican Metical
    
    Args:
        amount: Number to format
        symbol: Currency symbol
    
    Returns:
        str: Formatted currency string
    """
    if amount is None:
        return ""
    
    try:
        amount = float(amount)
        # Format with thousand separator and 2 decimal places
        formatted = "{:,.2f}".format(amount)
        return "{} {}".format(formatted, symbol)
    except (ValueError, TypeError):
        return str(amount)


# ============================================================
# Message Building Helpers
# ============================================================

def build_message_from_template(template, doc, extra_context=None):
    """
    Build a message from a Jinja2 template

    Args:
        template: Jinja2 template string
        doc: Document to use as context
        extra_context: Additional context variables

    Returns:
        str: Rendered message
    """
    from whatsapp_notifications.whatsapp_notifications.doctype.whatsapp_notification_rule.whatsapp_notification_rule import get_template_context

    context = get_template_context(doc)

    if extra_context:
        context.update(extra_context)

    return frappe.render_template(template, context)


# ============================================================
# Timeline Comment Helpers
# ============================================================

def add_whatsapp_comment(doctype, docname, comment_text, comment_type="Info"):
    """
    Add a comment to the document timeline for WhatsApp activity

    Args:
        doctype: Document type
        docname: Document name
        comment_text: Comment content (HTML supported)
        comment_type: Comment type (Info, Comment, etc.)
    """
    try:
        # Skip if doctype is a WhatsApp internal doctype
        if doctype in ("WhatsApp Message Log", "WhatsApp Approval Request",
                       "WhatsApp Approval Template", "Evolution API Settings"):
            return

        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": comment_type,
            "reference_doctype": doctype,
            "reference_name": docname,
            "content": comment_text
        }).insert(ignore_permissions=True)

    except Exception:
        # Don't let comment errors break the main flow
        pass


def format_phone_for_display(phone):
    """
    Format phone number for display in comments

    Args:
        phone: Phone number

    Returns:
        str: Formatted phone (e.g., "+258 841234567")
    """
    if not phone:
        return "desconhecido"

    phone = str(phone).strip()

    # Clean the phone number
    clean = re.sub(r'[^\d]', '', phone)

    if not clean:
        return phone

    # Format with country code prefix
    if len(clean) > 9:
        return "+{}".format(clean)
    else:
        return clean


def add_notification_sent_comment(doctype, docname, phone, recipient_name=None):
    """
    Add timeline comment for notification sent

    Args:
        doctype: Document type
        docname: Document name
        phone: Recipient phone number
        recipient_name: Recipient name (optional)
    """
    formatted_phone = format_phone_for_display(phone)

    if recipient_name:
        comment = "📱 <strong>WhatsApp:</strong> Notificação enviada para {} ({})".format(
            recipient_name, formatted_phone
        )
    else:
        comment = "📱 <strong>WhatsApp:</strong> Notificação enviada para {}".format(
            formatted_phone
        )

    add_whatsapp_comment(doctype, docname, comment)


def add_approval_sent_comment(doctype, docname, phone, template_name, recipient_name=None):
    """
    Add timeline comment for approval request sent

    Args:
        doctype: Document type
        docname: Document name
        phone: Recipient phone number
        template_name: Approval template name
        recipient_name: Recipient name (optional)
    """
    formatted_phone = format_phone_for_display(phone)

    if recipient_name:
        comment = "📱 <strong>WhatsApp:</strong> Pedido de aprovação enviado para {} ({}) - Template: {}".format(
            recipient_name, formatted_phone, template_name
        )
    else:
        comment = "📱 <strong>WhatsApp:</strong> Pedido de aprovação enviado para {} - Template: {}".format(
            formatted_phone, template_name
        )

    add_whatsapp_comment(doctype, docname, comment)


def add_approval_response_comment(doctype, docname, phone, option_label, status):
    """
    Add timeline comment for approval response received

    Args:
        doctype: Document type
        docname: Document name
        phone: Responder phone number
        option_label: Selected option label
        status: Resulting status (Approved/Rejected)
    """
    formatted_phone = format_phone_for_display(phone)

    # Choose icon based on status
    if status == "Approved":
        icon = "✅"
        status_text = "aprovado"
    elif status == "Rejected":
        icon = "❌"
        status_text = "rejeitado"
    else:
        icon = "📱"
        status_text = "respondido"

    comment = "{} <strong>WhatsApp:</strong> Documento {} pelo número {} (Resposta: {})".format(
        icon, status_text, formatted_phone, option_label
    )

    add_whatsapp_comment(doctype, docname, comment)


def truncate_message(message, max_length=4096):
    """
    Truncate message to WhatsApp's maximum length
    
    Args:
        message: Message to truncate
        max_length: Maximum length (WhatsApp supports ~65536, but 4096 is safe)
    
    Returns:
        str: Truncated message
    """
    if not message:
        return message
    
    if len(message) <= max_length:
        return message
    
    # Truncate and add indicator
    truncated = message[:max_length - 3]
    
    # Try to break at a word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_length - 50:
        truncated = truncated[:last_space]
    
    return truncated + "..."


# ============================================================
# Document Helpers
# ============================================================

def get_linked_doc_value(doctype, name, fieldname):
    """
    Safely get a value from a linked document
    
    Args:
        doctype: Linked document type
        name: Document name
        fieldname: Field to get
    
    Returns:
        Field value or None
    """
    if not doctype or not name or not fieldname:
        return None
    
    try:
        return frappe.db.get_value(doctype, name, fieldname)
    except Exception:
        return None


def get_contact_phone(contact_name):
    """
    Get primary phone number from a Contact
    
    Args:
        contact_name: Contact document name
    
    Returns:
        str: Phone number or None
    """
    if not contact_name:
        return None
    
    try:
        contact = frappe.get_doc("Contact", contact_name)
        
        # Check phone_nos child table
        if hasattr(contact, "phone_nos") and contact.phone_nos:
            for phone in contact.phone_nos:
                if phone.is_primary_mobile_no:
                    return phone.phone
            # If no primary, return first mobile
            for phone in contact.phone_nos:
                return phone.phone
        
        # Fallback to direct fields
        return contact.mobile_no or contact.phone
        
    except Exception:
        return None


def get_customer_phone(customer_name):
    """
    Get phone number for a Customer
    
    Args:
        customer_name: Customer document name
    
    Returns:
        str: Phone number or None
    """
    if not customer_name:
        return None
    
    try:
        # Try customer's primary contact
        primary_contact = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": "Customer",
                "link_name": customer_name,
                "parenttype": "Contact"
            },
            "parent"
        )
        
        if primary_contact:
            phone = get_contact_phone(primary_contact)
            if phone:
                return phone
        
        # Fallback to customer's direct phone
        return frappe.db.get_value("Customer", customer_name, "mobile_no")
        
    except Exception:
        return None
