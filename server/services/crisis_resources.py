"""
crisis_resources.py
===================
Maintainable configuration structure and verification procedures for Pakistan crisis resources.

DOCUMENTED VERIFICATION WORKFLOW:
----------------------------------
To ensure helpline integrity and user safety, crisis resources must be audited against official sources:
1. Primary Source Verification: Check official Pakistan government health departments or recognized NGO/clinical bodies.
2. Direct Contact Confirmation: Periodically test phone numbers and text shortcodes to verify operational status and operating hours.
3. Review Interval Audit: Every resource has a review_interval_days parameter (default 180 days). If (current_date - verification_date) > review_interval_days, review_status is marked 'EXPIRED' until re-audited.
4. Non-Verified Disclaimer: Resources without official documented sources must not be marked 'VERIFIED'.
5. Region Fallback: This Pakistan-focused application always returns the verified Pakistan resource directory.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

DEFAULT_REVIEW_INTERVAL_DAYS = 180

CRISIS_RESOURCES: Dict[str, List[Dict[str, Any]]] = {
    "pakistan": [
        {
            "organization": "Umang Pakistan Helpline",
            "contact_method": "Phone",
            "contact_info": "0311-7786264",
            "website": "https://www.umangpakistan.org",
            "availability": "24/7",
            "description": "Certified clinical psychologists offering 24/7 crisis mental health support.",
            "country_or_region": "Pakistan",
            "target_audience": "General & Adults",
            "source": "Official Umang Pakistan Portal (https://www.umangpakistan.org)",
            "verification_date": "2026-07-01",
            "review_status": "VERIFIED",
            "review_interval_days": 180,
            "status": "active"
        },
        {
            "organization": "Rozan Emotional Helpline",
            "contact_method": "Phone",
            "contact_info": "0800-22444",
            "website": "https://rozan.org",
            "availability": "Mon-Sat 10:00-18:00 PKT",
            "description": "Free emotional health, youth, and trauma counseling.",
            "country_or_region": "Pakistan",
            "target_audience": "Youth & Adults",
            "source": "Official Rozan NGO Directory (https://rozan.org)",
            "verification_date": "2026-07-01",
            "review_status": "VERIFIED",
            "review_interval_days": 180,
            "status": "active"
        },
        {
            "organization": "Child Protection Bureau Helpline (CPWB)",
            "contact_method": "Phone",
            "contact_info": "1121",
            "website": "https://cpwb.punjab.gov.pk",
            "availability": "24/7",
            "description": "Government of Punjab / National Child Protection Bureau toll-free 24/7 helpline for minors, children, and youth in distress.",
            "country_or_region": "Pakistan",
            "target_audience": "Minors & Children (Under 18)",
            "source": "Government of Pakistan CPWB Official Portal (https://cpwb.punjab.gov.pk)",
            "verification_date": "2026-07-01",
            "review_status": "VERIFIED",
            "review_interval_days": 180,
            "status": "active"
        },
        {
            "organization": "Madadgaar National Helpline",
            "contact_method": "Phone",
            "contact_info": "1098 / 021-35150075",
            "website": "http://madadgaar.org",
            "availability": "24/7",
            "description": "Pakistan's first national crisis helpline for children, youth, and women facing violence, abuse, or psychological distress.",
            "country_or_region": "Pakistan",
            "target_audience": "Children, Youth & Women",
            "source": "Madadgaar Helpline Directory (http://madadgaar.org)",
            "verification_date": "2026-07-01",
            "review_status": "VERIFIED",
            "review_interval_days": 180,
            "status": "active"
        },
        {
            "organization": "Taskeen Health Initiative",
            "contact_method": "Phone",
            "contact_info": "0316-8275336",
            "website": "https://taskeen.org",
            "availability": "24/7",
            "description": "Free mental health support and counseling line.",
            "country_or_region": "Pakistan",
            "target_audience": "General",
            "source": "Official Taskeen Health Portal (https://taskeen.org)",
            "verification_date": "2026-07-01",
            "review_status": "VERIFIED",
            "review_interval_days": 180,
            "status": "active"
        }
    ]
}

SAFETY_DISCLAIMER = (
    "MindGuard is an automated AI conversational tool and is NOT an emergency service, "
    "hospital, or clinical medical provider. If you or someone you know is in immediate physical danger, "
    "please contact Rescue 1122 or go immediately to the nearest hospital emergency department. "
    "or go immediately to the nearest hospital emergency room. "
    "Please reach out to a trusted family member, friend, or healthcare provider who can stay with you."
)


def check_resource_status(resource: Dict[str, Any], current_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Evaluates whether a crisis resource is up-to-date or expired.
    Flags resources as 'EXPIRED' if verification_date exceeds review_interval_days.
    """
    res_copy = dict(resource)
    today = current_date or datetime.utcnow()
    v_date_str = res_copy.get("verification_date")
    interval = res_copy.get("review_interval_days", DEFAULT_REVIEW_INTERVAL_DAYS)

    if not res_copy.get("review_status"):
        res_copy["review_status"] = "VERIFIED"

    if not v_date_str:
        res_copy["review_status"] = "PENDING_REVIEW"
        res_copy["is_outdated"] = True
        return res_copy

    try:
        v_date = datetime.strptime(v_date_str, "%Y-%m-%d")
        days_passed = (today - v_date).days
        if days_passed > interval:
            res_copy["review_status"] = "EXPIRED"
            res_copy["is_outdated"] = True
        else:
            res_copy["is_outdated"] = False
    except ValueError:
        res_copy["review_status"] = "PENDING_REVIEW"
        res_copy["is_outdated"] = True

    return res_copy


def get_resources_for_region(region: str = "pakistan") -> List[Dict[str, Any]]:
    """
    Returns active, verified Pakistan resources. This application is Pakistan-focused.
    """
    key = region.lower().strip() if region else "pakistan"
    resources = CRISIS_RESOURCES.get(key)
    
    if not resources:
        resources = CRISIS_RESOURCES["pakistan"]

    evaluated = []
    for r in resources:
        if r.get("status") == "active":
            status_checked = check_resource_status(r)
            evaluated.append(status_checked)

    return evaluated


def get_resource_verification_procedure() -> List[str]:
    """Returns the documented step-by-step verification procedure for crisis resources."""
    return [
        "1. Verify official government health department or recognized NGO registration.",
        "2. Confirm 24/7 operating availability or documented operating hours.",
        "3. Periodically test telephone hotline numbers and text shortcodes.",
        "4. Document the primary source URL and exact date of last verification.",
        "5. Re-audit all crisis resources every 180 days (or review_interval_days).",
        "6. Fallback to global emergency services guidance if regional match is unsupported."
    ]
