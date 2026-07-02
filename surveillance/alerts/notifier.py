"""Outbound alert notifications: webhook (Slack/Discord/generic JSON) and email.

Every function here is best-effort: network/SMTP failures are caught and
reported back as a status string rather than raised, so a bad SMTP password
in Settings never crashes the live monitoring loop.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests

from surveillance.alerts.engine import Alert
from surveillance.config import Settings


def send_webhook(settings: Settings, alert: Alert) -> tuple[bool, str]:
    if not settings.webhook_enabled or not settings.webhook_url:
        return False, "webhook disabled"
    payload = {
        "text": f"[SentryVision] {alert.severity.upper()} — {alert.message}",
        "site": settings.site_name,
        "camera": settings.camera_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "object_class": alert.object_class,
        "confidence": alert.confidence,
        "zone": alert.zone,
        "timestamp": alert.ts,
    }
    try:
        resp = requests.post(settings.webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        return True, f"webhook sent ({resp.status_code})"
    except requests.RequestException as exc:
        return False, f"webhook failed: {exc}"


def send_email(settings: Settings, alert: Alert) -> tuple[bool, str]:
    if not settings.email_enabled or not settings.smtp_host or not settings.email_to:
        return False, "email disabled"
    subject = f"[SentryVision] {alert.severity.upper()} alert at {settings.site_name}"
    body = (
        f"{alert.message}\n\n"
        f"Site: {settings.site_name}\n"
        f"Camera: {settings.camera_id}\n"
        f"Object: {alert.object_class} (confidence {alert.confidence:.0%})\n"
        f"Zone: {alert.zone or 'n/a'}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = settings.email_to

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], [settings.email_to], msg.as_string())
        return True, "email sent"
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"email failed: {exc}"


def dispatch(settings: Settings, alert: Alert) -> list[tuple[str, bool, str]]:
    """Fire all enabled notification channels for a single alert."""
    results: list[tuple[str, bool, str]] = []
    if settings.webhook_enabled:
        ok, msg = send_webhook(settings, alert)
        results.append(("webhook", ok, msg))
    if settings.email_enabled:
        ok, msg = send_email(settings, alert)
        results.append(("email", ok, msg))
    return results
