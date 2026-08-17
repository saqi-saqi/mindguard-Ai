# MindGuard Crisis Resources Maintenance & Verification Process

**Module Reference:** `server/crisis_resources.py`

---

## 1. Structure of Resource Records
Every crisis helpline entry must conform to the following schema in `server/crisis_resources.py`:

```python
{
    "organization": "Organization Name",
    "contact_method": "Phone | Text | Web",
    "contact_info": "Phone number or text shortcode",
    "website": "https://official-website-url",
    "availability": "24/7 or operating hours",
    "description": "Brief non-judgmental service description",
    "last_verified": "YYYY-MM-DD",
    "status": "active | inactive"
}
```

---

## 2. Review and Verification Schedule
1. **Quarterly Audit**: Every 3 months, test helpline numbers and verify website URLs.
2. **Updating Verification Date**: Update the `last_verified` ISO string for each tested entry.
3. **Deactivating Services**: If a hotline changes numbers or goes inactive, update `"status": "inactive"`. Inactive entries are automatically excluded from user-facing API responses (`get_resources_for_region`).

---

## 3. Mandatory Safety Principles
* **Non-Emergency Disclaimer**: Every safety response must display the clear disclaimer that MindGuard is an automated tool and NOT an emergency medical service.
* **Direct Helpline Access**: Hotline phone numbers and web URLs must be kept directly clickable for mobile and desktop users.
* **International Fallback**: The global fallback (`https://findahelpline.com`) must remain permanently active.
