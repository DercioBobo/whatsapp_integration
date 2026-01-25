"""
Create default Evolution API Settings if not exists
"""
import frappe


def execute():
    """Create default Evolution API Settings document"""
    if not frappe.db.exists("Evolution API Settings", "Evolution API Settings"):
        # The Single DocType will be created automatically when first accessed
        # We just need to ensure the module is properly set up
        pass
    
    frappe.db.commit()
