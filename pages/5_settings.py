"""Settings — site info, detection tuning, alert rules, notifications, and data retention."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dataclasses

import streamlit as st

from app_state import ensure_session_defaults, get_system, update_settings
from surveillance.alerts.notifier import send_email, send_webhook
from surveillance.config import COCO_CLASSES, DEFAULT_SECURITY_CLASSES

ensure_session_defaults()
system = get_system()
settings = system.settings

st.title("⚙️ Settings")

with st.form("settings_form"):
    st.markdown("### Site")
    c1, c2 = st.columns(2)
    site_name = c1.text_input("Site name", value=settings.site_name)
    camera_id = c2.text_input("Camera ID", value=settings.camera_id)

    st.divider()
    st.markdown("### Detection")
    c1, c2, c3 = st.columns(3)
    model_name = c1.selectbox(
        "Model", ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"],
        index=["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"].index(settings.model_name)
        if settings.model_name in ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"] else 0,
        help="n = fastest/lightest (recommended for CPU/edge), s/m = larger & more accurate.",
    )
    confidence = c2.slider("Confidence threshold", 0.1, 0.9, settings.confidence_threshold, 0.05)
    iou = c3.slider("IoU (NMS) threshold", 0.1, 0.9, settings.iou_threshold, 0.05)
    detection_classes = st.multiselect(
        "Classes to detect", COCO_CLASSES,
        default=settings.detection_classes or DEFAULT_SECURITY_CLASSES,
        help="Limiting classes speeds up inference and reduces noise.",
    )

    st.divider()
    st.markdown("### Alert Rules")
    c1, c2, c3 = st.columns(3)
    loiter_seconds = c1.number_input("Loitering threshold (seconds)", 3.0, 300.0,
                                      settings.loiter_seconds, 1.0)
    crowd_threshold = c2.number_input("Crowd threshold (people)", 2, 50, settings.crowd_threshold, 1)
    cooldown = c3.number_input("Alert cooldown (seconds)", 1.0, 600.0, settings.alert_cooldown_seconds, 1.0)

    armed = st.toggle("System Armed", value=settings.armed,
                       help="When off, detections still display but no alerts fire.")
    schedule_enabled = st.toggle("Use armed schedule (auto arm/disarm by time of day)",
                                  value=settings.schedule_enabled)
    c1, c2 = st.columns(2)
    armed_start = c1.slider("Armed from (hour, 24h)", 0, 23, settings.armed_start_hour,
                             disabled=not schedule_enabled)
    armed_end = c2.slider("Armed until (hour, 24h)", 0, 23, settings.armed_end_hour,
                           disabled=not schedule_enabled)

    st.divider()
    st.markdown("### Notifications")
    sound_alerts = st.toggle("Play sound on new alerts", value=settings.sound_alerts)

    webhook_enabled = st.toggle("Webhook notifications (Slack/Discord/generic JSON)",
                                 value=settings.webhook_enabled)
    webhook_url = st.text_input("Webhook URL", value=settings.webhook_url,
                                 disabled=not webhook_enabled, type="default")

    email_enabled = st.toggle("Email notifications", value=settings.email_enabled)
    ec1, ec2 = st.columns(2)
    smtp_host = ec1.text_input("SMTP host", value=settings.smtp_host, disabled=not email_enabled)
    smtp_port = ec2.number_input("SMTP port", 1, 65535, settings.smtp_port, disabled=not email_enabled)
    ec3, ec4 = st.columns(2)
    smtp_user = ec3.text_input("SMTP username", value=settings.smtp_user, disabled=not email_enabled)
    smtp_password = ec4.text_input("SMTP password", value=settings.smtp_password, type="password",
                                    disabled=not email_enabled)
    ec5, ec6 = st.columns(2)
    email_from = ec5.text_input("From address", value=settings.email_from, disabled=not email_enabled)
    email_to = ec6.text_input("To address", value=settings.email_to, disabled=not email_enabled)

    st.divider()
    st.markdown("### Data Retention")
    retention_days = st.number_input("Keep alerts & activity logs for (days)", 1, 365,
                                      settings.retention_days, 1)

    submitted = st.form_submit_button("💾 Save Settings", type="primary", width="stretch")

if submitted:
    new_settings = dataclasses.replace(
        settings,
        site_name=site_name, camera_id=camera_id,
        model_name=model_name, confidence_threshold=confidence, iou_threshold=iou,
        detection_classes=detection_classes,
        loiter_seconds=loiter_seconds, crowd_threshold=int(crowd_threshold),
        alert_cooldown_seconds=cooldown,
        armed=armed, schedule_enabled=schedule_enabled,
        armed_start_hour=int(armed_start), armed_end_hour=int(armed_end),
        sound_alerts=sound_alerts,
        webhook_enabled=webhook_enabled, webhook_url=webhook_url,
        email_enabled=email_enabled, smtp_host=smtp_host, smtp_port=int(smtp_port),
        smtp_user=smtp_user, smtp_password=smtp_password, email_from=email_from, email_to=email_to,
        retention_days=int(retention_days),
    )
    update_settings(new_settings)
    st.success("Settings saved.")
    st.rerun()

st.divider()
st.markdown("### Test Notifications")
tc1, tc2 = st.columns(2)
with tc1:
    if st.button("Send test webhook", disabled=not settings.webhook_enabled):
        from surveillance.alerts.engine import Alert
        import time as _time
        test_alert = Alert(_time.time(), "system", "info", "test", 1.0, None, None,
                            "This is a test alert from SentryVision AI Settings.")
        ok, msg = send_webhook(settings, test_alert)
        (st.success if ok else st.error)(msg)
with tc2:
    if st.button("Send test email", disabled=not settings.email_enabled):
        from surveillance.alerts.engine import Alert
        import time as _time
        test_alert = Alert(_time.time(), "system", "info", "test", 1.0, None, None,
                            "This is a test alert from SentryVision AI Settings.")
        ok, msg = send_email(settings, test_alert)
        (st.success if ok else st.error)(msg)

st.divider()
st.markdown("### Maintenance")
mc1, mc2 = st.columns(2)
with mc1:
    st.caption(f"Database: {system.store.total_counts()}")
with mc2:
    if st.button("🧹 Purge logs older than retention window"):
        n = system.store.purge_older_than(settings.retention_days)
        st.success(f"Purged {n} old record(s).")
