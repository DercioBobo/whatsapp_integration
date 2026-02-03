"""
Evolution API Settings - Configuration for WhatsApp Integration
Single DocType for storing Evolution API connection settings
"""
import frappe
from frappe.model.document import Document
from frappe import _


class EvolutionAPISettings(Document):
    """
    Single DocType for Evolution API configuration
    Stores connection details, phone formatting rules, and advanced settings
    """

    def onload(self):
        """Set webhook URL when document is loaded"""
        self.set_webhook_url()

    def set_webhook_url(self):
        """Generate and set the webhook URL for Evolution API"""
        site_url = frappe.utils.get_url()
        webhook_endpoint = "/api/method/whatsapp_notifications.whatsapp_notifications.webhook.receive_message"
        self.webhook_url = site_url + webhook_endpoint

    def validate(self):
        """Validate settings before save"""
        self.validate_api_url()
        self.validate_phone_settings()
    
    def validate_api_url(self):
        """Ensure API URL is properly formatted"""
        if self.api_url:
            # Remove trailing slash
            self.api_url = self.api_url.rstrip("/")
            
            # Ensure it starts with http:// or https://
            if not self.api_url.startswith(("http://", "https://")):
                frappe.throw(_("API URL must start with http:// or https://"))
    
    def validate_phone_settings(self):
        """Validate phone number configuration"""
        if self.default_country_code:
            # Remove any non-numeric characters
            self.default_country_code = "".join(
                c for c in str(self.default_country_code) if c.isdigit()
            )
        
        if self.local_number_length and self.local_number_length < 5:
            frappe.throw(_("Local number length must be at least 5 digits"))
    
    def on_update(self):
        """Clear cache when settings change"""
        frappe.cache().delete_key("evolution_api_settings")
    
    @frappe.whitelist()
    def configure_webhook(self):
        """
        Configure webhook in Evolution API to receive incoming messages
        """
        if not self.api_url or not self.api_key or not self.instance_name:
            return {
                "success": False,
                "message": _("Please configure API URL, API Key, and Instance Name first")
            }

        try:
            # Build webhook URL
            site_url = frappe.utils.get_url()
            webhook_endpoint = "/api/method/whatsapp_notifications.whatsapp_notifications.webhook.receive_message"
            webhook_url = site_url + webhook_endpoint

            # Build API request
            url = "{}/webhook/set/{}".format(
                self.api_url, self.instance_name
            )

            headers = {
                "Content-Type": "application/json",
                "apikey": self.get_password("api_key") or self.api_key
            }

            payload = {
                "webhook": {
                    "enabled": True,
                    "url": webhook_url,
                    "headers": {
                        "Content-Type": "application/json"
                    },
                    "byEvents": True,
                    "base64": False,
                    "events": [
                        "MESSAGES_UPSERT"
                    ]
                }
            }

            # Make request
            response = make_request("POST", url, headers=headers, data=payload)

            if response:
                self.db_set("webhook_status", "Configured - {}".format(frappe.utils.now()))
                return {
                    "success": True,
                    "message": _("Webhook configured successfully in Evolution API"),
                    "webhook_url": webhook_url
                }
            else:
                self.db_set("webhook_status", "Error: No response")
                return {
                    "success": False,
                    "message": _("No response from Evolution API")
                }

        except Exception as e:
            error_msg = str(e)
            self.db_set("webhook_status", "Error: {}".format(error_msg[:100]))

            frappe.log_error(
                "Evolution API Webhook Configuration Failed: {}".format(error_msg),
                "WhatsApp Webhook Error"
            )

            return {
                "success": False,
                "message": _("Failed to configure webhook: {}").format(error_msg)
            }

    @frappe.whitelist()
    def get_webhook_status(self):
        """
        Get current webhook configuration from Evolution API
        """
        if not self.api_url or not self.api_key or not self.instance_name:
            return {
                "success": False,
                "message": _("Please configure API URL, API Key, and Instance Name first")
            }

        try:
            url = "{}/webhook/find/{}".format(
                self.api_url, self.instance_name
            )

            headers = {
                "Content-Type": "application/json",
                "apikey": self.get_password("api_key") or self.api_key
            }

            response = make_request("GET", url, headers=headers)

            if response:
                webhook_data = response.get("webhook", response)
                return {
                    "success": True,
                    "enabled": webhook_data.get("enabled", False),
                    "url": webhook_data.get("url", ""),
                    "events": webhook_data.get("events", [])
                }
            else:
                return {
                    "success": False,
                    "message": _("No webhook configuration found")
                }

        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    @frappe.whitelist()
    def test_connection(self):
        """
        Test the Evolution API connection
        Returns connection status and updates the document
        """
        if not self.api_url or not self.api_key or not self.instance_name:
            return {
                "success": False,
                "message": _("Please configure API URL, API Key, and Instance Name")
            }
        
        try:
            # Test connection by checking instance status
            url = "{}/instance/connectionState/{}".format(
                self.api_url, self.instance_name
            )
            
            headers = {
                "Content-Type": "application/json",
                "apikey": self.get_password("api_key") or self.api_key
            }
            
            # Use frappe's HTTP method (works in v13-v15)
            response = make_request("GET", url, headers=headers)
            
            if response and response.get("instance"):
                state = response.get("instance", {}).get("state", "unknown")
                self.db_set("connection_status", "Connected ({})".format(state))
                self.db_set("last_checked", frappe.utils.now())
                
                return {
                    "success": True,
                    "message": _("Connection successful! Instance state: {}").format(state),
                    "state": state
                }
            else:
                self.db_set("connection_status", "Error: Invalid response")
                self.db_set("last_checked", frappe.utils.now())
                
                return {
                    "success": False,
                    "message": _("Invalid response from Evolution API")
                }
                
        except Exception as e:
            error_msg = str(e)
            self.db_set("connection_status", "Error: {}".format(error_msg[:100]))
            self.db_set("last_checked", frappe.utils.now())
            
            frappe.log_error(
                "Evolution API Connection Test Failed: {}".format(error_msg),
                "WhatsApp Connection Error"
            )
            
            return {
                "success": False,
                "message": _("Connection failed: {}").format(error_msg)
            }


def get_settings():
    """
    Get cached Evolution API Settings
    Returns dict with all settings for easy access
    """
    settings = frappe.cache().get_value("evolution_api_settings")

    if not settings:
        try:
            doc = frappe.get_single("Evolution API Settings")

            # Get media doctypes child table
            media_doctypes = []
            if hasattr(doc, 'media_doctypes') and doc.media_doctypes:
                for row in doc.media_doctypes:
                    media_doctypes.append({
                        "document_type": row.document_type,
                        "phone_field": row.phone_field,
                        "default_print_format": row.default_print_format,
                        "caption_template": row.caption_template
                    })

            settings = {
                "enabled": doc.enabled,
                "api_url": doc.api_url,
                "api_key": doc.get_password("api_key") if doc.api_key else None,
                "instance_name": doc.instance_name,
                "default_country_code": doc.default_country_code or "258",
                "local_number_length": doc.local_number_length or 9,
                "local_number_prefixes": (doc.local_number_prefixes or "").split(","),
                "owner_number": doc.owner_number,
                "timeout_seconds": doc.timeout_seconds or 30,
                "max_retries": doc.max_retries or 3,
                "retry_delay_minutes": doc.retry_delay_minutes or 5,
                "log_retention_days": doc.log_retention_days or 30,
                "enable_debug_logging": doc.enable_debug_logging,
                "enable_rate_limiting": doc.enable_rate_limiting,
                "messages_per_minute": doc.messages_per_minute or 20,
                "queue_enabled": doc.queue_enabled,
                "media_doctypes": media_doctypes,
            }
            frappe.cache().set_value("evolution_api_settings", settings, expires_in_sec=300)
        except Exception:
            # Return defaults if settings don't exist
            settings = {
                "enabled": False,
                "api_url": None,
                "api_key": None,
                "instance_name": None,
                "default_country_code": "258",
                "local_number_length": 9,
                "local_number_prefixes": ["82", "83", "84", "85", "86", "87"],
                "owner_number": None,
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_minutes": 5,
                "log_retention_days": 30,
                "enable_debug_logging": False,
                "enable_rate_limiting": False,
                "messages_per_minute": 20,
                "queue_enabled": True,
                "media_doctypes": [],
            }

    return settings


def make_request(method, url, headers=None, data=None):
    """
    Make HTTP request compatible with v13-v15
    """
    import json

    headers = headers or {}

    # Method 1: frappe.integrations.utils (v14+)
    try:
        from frappe.integrations.utils import make_post_request, make_get_request

        if method.upper() == "GET":
            return make_get_request(url, headers=headers)
        elif method.upper() == "POST":
            if isinstance(data, dict):
                # Try with json parameter first
                try:
                    return make_post_request(url, headers=headers, json=data)
                except TypeError:
                    # Fallback: encode manually
                    headers["Content-Type"] = "application/json; charset=utf-8"
                    return make_post_request(url, headers=headers, data=json.dumps(data, ensure_ascii=False).encode("utf-8"))
            else:
                return make_post_request(url, headers=headers, data=data)

    except ImportError:
        pass
    except Exception as e:
        # Log but continue to fallback
        frappe.log_error(
            "integrations.utils failed: {} - trying fallback".format(str(e)),
            "WhatsApp HTTP Debug"
        )

    # Method 2: requests library (fallback)
    try:
        import requests

        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method.upper() == "POST":
            if isinstance(data, dict):
                headers["Content-Type"] = "application/json; charset=utf-8"
                response = requests.post(url, headers=headers, json=data, timeout=60)
            else:
                response = requests.post(url, headers=headers, data=data, timeout=60)
        else:
            raise ValueError("Unsupported HTTP method: {}".format(method))

        if not response.ok:
            raise Exception("HTTP {}: {}".format(response.status_code, response.text[:500]))

        return response.json()

    except Exception as e:
        frappe.log_error(
            "HTTP Request Failed: {} {} - {}".format(method, url, str(e)),
            "WhatsApp HTTP Error"
        )
        raise


@frappe.whitelist()
def test_api_connection():
    """Whitelist method to test connection from client"""
    settings = frappe.get_single("Evolution API Settings")
    return settings.test_connection()
