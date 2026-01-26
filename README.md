# WhatsApp Notifications for ERPNext

A flexible, event-driven WhatsApp notification service for ERPNext using Evolution API. Works with any DocType (standard or custom) across ERPNext v13, v14, and v15.

## Features

- **Universal DocType Support**: Configure notifications for ANY DocType
- **Event-Driven Triggers**: Send messages on Insert, Update, Submit, Cancel, or custom conditions
- **Template System**: Dynamic message templates with Jinja2 support
- **Phone Number Formatting**: Automatic country code handling (configurable)
- **Message Logging**: Complete audit trail of all sent messages
- **Retry Mechanism**: Automatic retry for failed messages
- **Bulk Messaging**: Queue-based sending for high volume
- **Multi-Instance**: Support multiple Evolution API instances
- **v13-v15 Compatible**: Works across all supported ERPNext versions

## Requirements

- ERPNext v13.x, v14.x, or v15.x
- Evolution API instance (self-hosted or cloud)
- WhatsApp Business account connected to Evolution API

## Installation

### Via Bench (Recommended)

```bash
# Get the app
bench get-app https://github.com/your-username/whatsapp_notifications

# Install on your site
bench --site your-site.local install-app whatsapp_notifications

# Run migrations
bench --site your-site.local migrate
```

### Manual Installation

```bash
cd frappe-bench/apps
git clone https://github.com/your-username/whatsapp_notifications
cd ..
bench --site your-site.local install-app whatsapp_notifications
bench --site your-site.local migrate
```

## Configuration

### 1. Evolution API Settings

Navigate to: **WhatsApp Notifications > Evolution API Settings**

| Field | Description |
|-------|-------------|
| Enabled | Master switch for the integration |
| API URL | Your Evolution API base URL (e.g., `http://your-server:8080`) |
| API Key | Authentication key from Evolution API |
| Instance Name | WhatsApp instance name in Evolution API |
| Default Country Code | Default country code for phone formatting (e.g., `258` for Mozambique) |
| Owner Number | Business owner's WhatsApp number for admin notifications |

### 2. Create Notification Rules

Navigate to: **WhatsApp Notifications > WhatsApp Notification Rule**

Configure when and what to send:

| Field | Description |
|-------|-------------|
| Rule Name | Descriptive name for the rule |
| DocType | Target DocType (e.g., `Sales Order`, `Lead`, `Customer`) |
| Event | Trigger event: `After Insert`, `On Update`, `On Submit`, `On Cancel`, `On Change` |
| Condition | Optional: Jinja2 condition (e.g., `{{ doc.status == "Approved" }}`) |
| Phone Field | Field containing recipient's phone (e.g., `mobile_no`, `phone`) |
| Message Template | Jinja2 template for the message content |
| Notify Owner | Also send notification to business owner |
| Owner Message | Separate template for owner notification |
| Enabled | Toggle rule on/off |

## Message Templates

Use Jinja2 syntax to create dynamic messages:

```jinja
Olá {{ doc.customer_name }},

Seu pedido *{{ doc.name }}* foi confirmado!

Itens: {{ doc.items | length }}
Total: *{{ doc.grand_total | round(2) }} MZN*

Obrigado pela preferência!
```

### Available Variables

- `doc` - The current document object
- `frappe` - Frappe utilities
- `nowdate` - Current date
- `nowtime` - Current time
- `format_date` - Date formatting function
- `format_currency` - Currency formatting function

### Formatting

WhatsApp supports basic formatting:
- `*bold*` - Bold text
- `_italic_` - Italic text
- `~strikethrough~` - Strikethrough
- ``` `code` ``` - Monospace

## Phone Number Handling

The app automatically formats phone numbers:

1. Removes spaces, dashes, and special characters
2. Strips leading `+` signs
3. Adds country code if number appears local

### Mozambique Example
- Input: `84 123 4567` → Output: `258841234567`
- Input: `+258841234567` → Output: `258841234567`
- Input: `258841234567` → Output: `258841234567`

### Configuration

Set the default country code in Evolution API Settings. The app detects local numbers by:
- Length (typically 9 digits for local)
- Starting digit patterns (customizable per country)

## API Methods

### Send WhatsApp (Manual)

```python
import frappe

# Via whitelisted method
frappe.call(
    "whatsapp_notifications.whatsapp_notifications.api.send_whatsapp",
    phone="841234567",
    message="Hello from ERPNext!",
    doctype="Sales Order",  # Optional: for logging
    docname="SO-0001"       # Optional: for logging
)
```

### Send via Document

```python
# In any Python script
from whatsapp_notifications.whatsapp_notifications.api import send_whatsapp_notification

send_whatsapp_notification(
    phone="841234567",
    message="Your message here",
    reference_doctype="Customer",
    reference_name="CUST-0001"
)
```

### JavaScript (Client-side)

```javascript
frappe.call({
    method: 'whatsapp_notifications.whatsapp_notifications.api.send_whatsapp',
    args: {
        phone: '841234567',
        message: 'Hello from ERPNext!'
    },
    callback: function(r) {
        if (r.message && r.message.success) {
            frappe.show_alert({
                message: __('WhatsApp sent!'),
                indicator: 'green'
            });
        }
    }
});
```

## Message Logs

All messages are logged in **WhatsApp Message Log**:

- Recipient phone number
- Message content
- Send status (Pending, Sent, Failed)
- Error details (if failed)
- Reference document
- Timestamps
- Retry count

## Troubleshooting

### Common Issues

**1. Messages not sending**
- Check Evolution API Settings are configured
- Verify API Key is correct
- Ensure instance is connected in Evolution API dashboard
- Check Error Log for details

**2. Phone number formatting issues**
- Verify country code is set correctly
- Check the phone field contains valid numbers
- Review phone format patterns in settings

**3. Template errors**
- Check Jinja2 syntax in message templates
- Verify field names match your DocType
- Test with simple templates first

### Debug Mode

Enable debug logging:

```python
# In bench console
frappe.conf.whatsapp_debug = True
```

View logs:
```bash
bench --site your-site.local console
>>> frappe.get_all("Error Log", filters={"method": ["like", "%whatsapp%"]})
```

## Upgrade Guide

### From Custom Scripts to App

If you're migrating from custom server scripts:

1. Install the app
2. Create notification rules matching your existing triggers
3. Copy message templates
4. Disable old server scripts
5. Test thoroughly

## Development

### Running Tests

```bash
bench --site test_site run-tests --app whatsapp_notifications
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE)

## Support

- GitHub Issues: [Report a bug](https://github.com/your-username/whatsapp_notifications/issues)
- Documentation: [Wiki](https://github.com/your-username/whatsapp_notifications/wiki)

## Changelog

### v1.0.0
- Initial release
- Evolution API integration
- Event-driven notifications
- Message templates
- Phone number formatting
- Message logging
- v13-v15 compatibility
