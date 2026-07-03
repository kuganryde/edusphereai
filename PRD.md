# SentryVision AI — Product Requirements Document

| | |
|---|---|
| **Product** | SentryVision AI |
| **Type** | AI-powered CCTV surveillance & analysis platform |
| **Target deployment** | Guard houses, sentry posts, gatehouses, small perimeter checkpoints |
| **Stack** | 100% Python (Streamlit UI + backend, OpenCV, Ultralytics YOLOv8) |
| **Status** | v1.0 — implemented, tested, documented |
| **Owner** | RydeTechWiz Solutions |
| **Last updated** | 2026-07-02 |

---

## 1. Problem Statement

Guard houses and sentry posts are the first line of physical security for a
site, but the humans staffing them are subject to fatigue, distraction, and
blind spots — a guard cannot watch six monitors with equal attention for an
entire shift. Commercial CCTV/VMS suites that add AI analytics (Milestone,
Genetec, Avigilon, etc.) are expensive, closed-source, hardware-locked, and
overkill for a single guard post or small site. Open-source computer-vision
tooling exists, but it's scattered across scripts, notebooks, and
demos — there's no cohesive, install-and-run application built for this
specific job.

**SentryVision AI** closes that gap: a single, self-contained Python
application a guard house can run on ordinary hardware, with AI object
detection, configurable restricted zones, real-time alerting, and an
analytics dashboard — an interactive tool a non-programmer guard/security
supervisor can operate, not a research script.

## 2. Goals

1. **Detect and classify** people, vehicles, and flagged objects in a video
   feed in real time using a modern CNN object detector (YOLOv8).
2. **Alert on security-relevant events**: intrusion into a restricted zone,
   loitering/dwell time, crowding, and flagged objects — with configurable
   thresholds and cooldowns so alerts are actionable, not noisy.
3. **Give a guard an operational picture in seconds**: live annotated video,
   a rolling alert feed, a searchable event log with snapshots, and
   analytics trends — no training required beyond "click Start Monitoring."
4. **Work with whatever video source is available**: a webcam on the guard
   house PC, an RTSP/IP camera, an uploaded/recorded video for review, or a
   built-in simulated scene for demoing/testing without any camera at all.
5. **Never hard-fail.** If the AI model can't be loaded (no network,
   unsupported hardware), the system degrades to classical motion detection
   automatically rather than refusing to run — a guard house cannot afford
   a monitoring blackout because of a dependency hiccup.
6. **Be entirely Python**, installable with one command (`uv sync`), so it
   can be deployed, forked, and extended by a security team without a
   separate frontend build step or a different language for the backend.

### Non-goals (v1)

- Facial recognition / biometric identity matching.
- Firearm/weapon detection (would require a custom-trained model beyond
  stock COCO classes — documented as a known limitation, see §9).
- Multi-camera synchronized dashboards (v1 is single-camera per session;
  the architecture doesn't preclude adding this later — see §10 Roadmap).
- Video storage/DVR functionality (SentryVision alerts and snapshots, it
  does not replace an NVR's continuous recording).

## 3. Target Users & Personas

| Persona | Need |
|---|---|
| **Gate guard / sentry** | Wants a live feed with obvious visual/audio cues when something needs attention — not a wall of raw video to stare at. |
| **Security supervisor** | Wants to define what "suspicious" means for *this* site (zones, thresholds, arm schedule) and review what happened on a shift after the fact. |
| **Site facilities/IT** | Wants something they can install on existing hardware, that doesn't need a cloud subscription, and that degrades safely if the network or GPU isn't available. |

## 4. Functional Requirements

### 4.1 Video Ingestion
- **Local webcam** — any camera attached to the machine running the app
  (`cv2.VideoCapture` device index).
- **RTSP / IP camera** — the standard protocol used by real CCTV hardware;
  connection is bounded to a 5s timeout so a bad URL fails fast with a
  clear error instead of freezing the UI. Forced over TCP transport by
  default to avoid the frame corruption/dropped-connection errors that
  RTSP's default UDP transport produces on lossy Wi-Fi/consumer-camera
  links.
- **Uploaded video file** — for reviewing recorded footage or testing
  configuration changes against a known clip; loops continuously.
- **Simulated demo scene** — a procedurally generated guard-house gate
  scene (no camera, network, or model download required) used for
  training, UI testing, and zero-dependency demos. It reports its own
  ground-truth detections rather than asking a real detector to recognize
  cartoon shapes, and is clearly labeled "Simulated" throughout the UI.

### 4.2 Object Detection
- Primary backend: **Ultralytics YOLOv8** (nano/small/medium selectable),
  running on CPU by default.
- Configurable confidence and IoU/NMS thresholds.
- Configurable class filter — defaults to a curated "security relevant"
  subset (person, vehicles, bags, dog, knife, scissors) rather than all 80
  COCO classes, to reduce noise.
- **Automatic fallback**: if YOLOv8 weights can't be loaded (no
  `ultralytics`/`torch`, or no network to fetch weights on first run,
  bounded to a 12s timeout), the system transparently switches to OpenCV
  background-subtraction motion detection. The active backend is always
  shown in the UI so an operator knows exactly what's running and why.

### 4.3 Multi-Object Tracking
- Lightweight centroid tracker assigns a stable ID to each detected object
  across frames, enabling dwell-time (loitering) measurement per zone.

### 4.4 Zones & Rules
- Operators draw **restricted** zones (alert on entry) or **watch** zones
  (loitering/occupancy only, no entry alert) over a live snapshot, via:
  - a **Quick Rectangle** slider tool with a live visual preview, or
  - a **Precise Coordinates** table for arbitrary polygons.
- Each zone specifies which object classes it cares about (e.g. a vehicle
  gate zone watches for `car`/`truck`, not `dog`).
- Zones persist to disk and apply immediately on the next monitoring
  session.

### 4.5 Alerting
- **Intrusion**: a watched class enters a restricted zone.
- **Loitering**: a tracked object dwells in any zone past a configurable
  threshold (seconds).
- **Crowd**: total person-like count in frame exceeds a configurable
  threshold.
- **Flagged object**: a class in the "threat-adjacent" set (e.g. knife,
  scissors) is detected anywhere, regardless of zone.
- Every rule respects a **cooldown window** per (rule, zone/track) so a
  stationary object doesn't spam duplicate alerts.
- **Arm/disarm**: alerts can be globally armed/disarmed, or auto-scheduled
  by hour of day (e.g. only armed after hours).
- **Notification channels**: in-app sound + visual feed, outbound webhook
  (Slack/Discord/generic JSON), and SMTP email — each independently
  configurable and testable from Settings, and each fails soft (a bad SMTP
  password logs an error, it never crashes monitoring).

### 4.6 Event Log & Snapshots
- Every alert is persisted (SQLite) with timestamp, type, severity, object
  class, confidence, zone, and — for warning/critical alerts — a saved
  JPEG snapshot of the frame.
- Searchable/filterable by type and acknowledgment state; alerts can be
  acknowledged; the log is exportable to CSV.

### 4.7 Analytics
- Time-windowed (last hour / 24h / 7d / all-time) dashboards: activity
  over time, detections by class, alerts by hour-of-day, alerts by zone,
  and alert severity breakdown.

### 4.8 Settings
- Site name/camera ID, detection tuning, alert thresholds, arm schedule,
  notification channels, and data retention — all in one form, persisted
  to disk, applied live without restarting the app.

## 5. Non-Functional Requirements

| Requirement | Approach |
|---|---|
| **Runs with zero configuration** | Sensible defaults everywhere; the Demo Scene requires no camera/model/network to fully exercise the product. |
| **Never blocks the UI indefinitely** | Model loading (12s) and RTSP connection (5s) are both hard-timeout-bounded on a worker thread; a network outage degrades functionality, it doesn't hang the app. |
| **CPU-friendly** | YOLOv8-nano by default; motion-detection fallback has near-zero overhead. |
| **Data stays local** | SQLite + local JPEG snapshots + local JSON config — no cloud dependency, no telemetry. |
| **Extensible** | Detection, tracking, alerting, storage, and UI are separate modules (`surveillance/` package) with narrow interfaces — swapping the detector backend or adding a new alert rule doesn't touch the UI layer. |
| **Testable** | Core logic (zones, tracker, alert engine, storage, analytics, detector fallback) has unit test coverage independent of any camera or browser. |

## 6. User Experience Principles

- **One click to start seeing value**: Live Monitor defaults to the Demo
  Scene so "Start Monitoring" produces a working, alerting system
  immediately — evaluation doesn't require camera hardware or model
  downloads.
- **Always show system state**: armed/disarmed, detection backend
  (AI vs. fallback), FPS, and object counts are always visible on the
  video overlay and the page header, not buried in logs.
- **Configuration is visual, not just numeric**: zones are drawn/previewed
  on the actual camera view; nothing requires hand-editing JSON (though
  it's there on disk for power users/automation).
- **Alerts explain themselves**: every alert message states what happened
  in plain language ("Person entered restricted zone 'Gate Restricted
  Area'"), not a rule ID.

## 7. Success Metrics

- **Time-to-first-alert**: a new operator can go from opening the app to
  seeing a real alert (via the Demo Scene) in under 60 seconds.
- **Zero unhandled exceptions** across the full feature surface (verified
  in this release via automated browser walkthroughs of every page and
  workflow — see the accompanying Architecture doc, §"Verification").
- **Bounded worst-case latency**: no user action should be able to freeze
  the UI for longer than the documented timeouts (12s model load, 5s RTSP
  connect).

## 8. System Architecture (summary)

See `docs/ARCHITECTURE.md` for the full technical breakdown. In brief:

```
Video Source → Object Detector → Tracker → Alert Engine → Event Store
   (webcam/         (YOLOv8 or         (centroid    (zones + rules)  (SQLite +
    RTSP/file/       motion fallback)   IDs +                         snapshots)
    demo)                               dwell time)
                                                            ↓
                                              Notifier (sound/webhook/email)

All of the above is orchestrated per-session by the Streamlit UI
(Live Monitor / Zone Editor / Event Log / Analytics / Settings pages).
```

## 9. Known Limitations

- **No firearm detection.** Stock COCO (the dataset YOLOv8's bundled
  weights are trained on) has no gun/rifle class. `knife` and `scissors`
  are flagged as "threat-adjacent," but true weapon detection would
  require a custom-trained model — out of scope for v1, noted as a
  roadmap item.
- **Centroid tracker, not a full MOT model.** It's fast and dependency-free
  but can mis-associate IDs under heavy occlusion or very fast motion; good
  enough for a single-camera gate/entrance scene, not crowd-scale tracking.
- **Single camera per session.** The architecture (`SurveillanceSystem`)
  is per-camera; running multiple cameras today means multiple app
  instances, not a unified multi-feed dashboard (see Roadmap).
- **Model download requires network access on first run.** In fully
  air-gapped environments, an operator must pre-place YOLOv8 weights in
  `data/models/` manually; the app cleanly falls back to motion detection
  in the meantime rather than failing to start.

## 10. Roadmap (post-v1)

1. Multi-camera grid view with a shared alert feed.
2. Pluggable custom-trained detectors (e.g. a weapon-detection model) via
   the same `ObjectDetector` interface.
3. Line-crossing (tripwire) rules in addition to polygon zones.
4. Role-based access (guard vs. supervisor views) and audit log of
   setting changes.
5. Edge deployment guide (Raspberry Pi / Jetson) with a quantized model.
