"""
WhatsApp Notifications - Installation and Migration Hooks
"""
import frappe


def after_install():
    """
    Run after the app is installed
    Creates default settings and sets up initial configuration
    """
    create_default_settings()
    print("WhatsApp Notifications installed successfully!")


def after_migrate():
    """
    Run after each migration
    Ensures settings exist and updates any cached data
    """
    create_default_settings()
    clear_notification_cache()


def create_default_settings():
    """
    Create Evolution API Settings if it doesn't exist
    Single DocTypes are created automatically, but we ensure defaults are set
    """
    try:
        # Check if settings exist
        if frappe.db.exists("DocType", "Evolution API Settings"):
            settings = frappe.get_single("Evolution API Settings")
            
            # Set defaults if not configured
            if not settings.default_country_code:
                settings.default_country_code = "258"  # Mozambique
                settings.save(ignore_permissions=True)
                frappe.db.commit()
    except Exception as e:
        # Silently ignore if DocType doesn't exist yet (first install)
        pass


def clear_notification_cache():
    """
    Clear cached notification rules
    Called after migration to ensure rules are reloaded
    """
    try:
        frappe.cache().delete_key("whatsapp_notification_rules")
        frappe.cache().delete_key("whatsapp_notification_doctypes")
    except Exception:
        pass


def before_tests():
    """
    Setup test environment
    """
    # Create test settings
    frappe.get_doc({
        "doctype": "Evolution API Settings",
        "enabled": 0,
        "api_url": "http://localhost:8080",
        "api_key": "test-key",
        "instance_name": "test",
        "default_country_code": "258"
    }).save(ignore_permissions=True)
