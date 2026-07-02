# SentryVision AI — Architecture

Technical reference for the codebase. For the product rationale, see
[`PRD.md`](../PRD.md). For setup/usage, see [`README.md`](../README.md).

## 1. Design principles

1. **The backend never imports Streamlit.** Everything under `surveillance/`
   is plain Python — testable with `pytest`, no browser or session state
   required. Only `app_state.py`, `streamlit_app.py`, and `pages/*.py`
   touch `streamlit`.
2. **Every I/O boundary degrades instead of crashing.** Camera
   unreachable, model unavailable, SMTP down, webhook down, corrupt
   settings file — each has an explicit fallback path and a bounded
   timeout where the underlying library doesn't provide one.
3. **One `SurveillanceSystem` object per process**, cached via
   `st.cache_resource`, holds the detector/tracker/alert-engine/store so
   the (potentially slow) model load happens once, not on every rerun.

## 2. Package layout

```
streamlit_app.py           Entry point: page config + st.navigation
app_state.py                Streamlit-facing glue: cached resources, session helpers
pages/
  1_live_monitor.py         Main dashboard: video + overlays + live alert feed
  2_zone_editor.py          Draw/manage restricted & watch zones
  3_event_log.py            Alert history, filtering, acknowledgment, snapshots
  4_analytics.py            Charts: activity, class distribution, alerts by hour/zone
  5_settings.py             Site/detection/alerting/notification/retention config

surveillance/                       Framework-agnostic backend package
  types.py                          Detection dataclass (shared, dependency-free)
  config.py                         Settings dataclass + persisted JSON + paths + COCO class list
  zones.py                          Zone dataclass, point-in-polygon geometry, persistence
  system.py                         SurveillanceSystem: wires detector+tracker+alerts+store together
  video/
    stream.py                       FrameSource ABC + Webcam/RTSP/File/Demo implementations
  detection/
    detector.py                     ObjectDetector: YOLOv8 backend with motion-detection fallback
    tracker.py                      CentroidTracker: per-object IDs + zone dwell time
  alerts/
    engine.py                       AlertEngine: intrusion/loitering/crowd/threat rules + cooldowns
    notifier.py                     Webhook + email dispatch (best-effort, never raises)
  storage/
    db.py                           EventStore: SQLite persistence for alerts + frame stats
  analytics/
    metrics.py                      Row → pandas DataFrame helpers for the Analytics page
  utils/
    drawing.py                      OpenCV overlay rendering (boxes, zones, HUD)
    audio.py                        Synthesized alert tone (no bundled audio asset)

tests/                       Unit tests for everything under surveillance/ (no camera/browser needed)
data/                         Runtime data (gitignored): sentryvision.db, zones.json, settings.json,
                               snapshots/*.jpg, models/*.pt
```

## 3. Data flow (one frame, Live Monitor loop)

```
FrameSource.read() → np.ndarray (BGR, 960x540)
        │
        ├─ if DemoSource: source.simulated_detections() → list[Detection]  (ground truth, no model)
        └─ else: ObjectDetector.infer(frame) → list[Detection]              (YOLOv8 or motion fallback)
                │
                ▼
        CentroidTracker.update(detections)     — mutates detections in place, assigns .track_id
                │
                ▼
        AlertEngine.evaluate(detections, zones, w, h, tracker) → list[Alert]
                │  (per detection: zone membership test, dwell time via tracker.set_zone,
                │   cooldown-gated intrusion/loitering/threat rules; crowd rule over the whole frame)
                ▼
        for each Alert:
          EventStore.log_alert(...)             — SQLite row + JPEG snapshot on disk
          notifier.dispatch(settings, alert)     — webhook / email, best-effort
                │
                ▼
        draw_zones() → draw_detections() → draw_hud()   — overlay rendering (OpenCV)
                │
                ▼
        st.image(...) into a placeholder            — no full script rerun per frame
```

The Live Monitor page runs this as a `while` loop inside a single Streamlit
script execution (not a rerun per frame), updating `st.empty()` placeholders
in place. Streamlit's cooperative cancellation (a new widget interaction —
e.g. clicking "Stop" — interrupts the running script at the next `st.*`
call) is what makes the Stop button responsive without extra plumbing.

## 4. Key design decisions & why

### 4.1 Detector fallback instead of a hard dependency on YOLOv8/torch

`ObjectDetector` tries to load Ultralytics YOLOv8 in `_load_yolo()`. Two
failure modes are handled explicitly:

- **`ultralytics` not installed** → immediate fallback, no delay.
- **Weights unreachable** (no network, blocked host, corrupt cache) →
  this is the interesting case. Ultralytics' own retry/backoff logic has
  **no reliable timeout when it isn't running on the main thread** (some
  of its dependencies use signal-based timeouts, which are a no-op outside
  the main thread — exactly the situation inside a Streamlit
  `ScriptRunner` worker thread). Left unbounded, this can hang the whole
  page indefinitely. `_load_yolo()` therefore runs the load on its own
  worker thread and does `thread.join(timeout=MODEL_LOAD_TIMEOUT_SECONDS)`
  (12s) — a timeout mechanism that works regardless of which thread called
  it. If it doesn't finish in time, the detector falls back to motion
  detection immediately; the abandoned thread is daemonized so it doesn't
  block process exit.

- Downloaded weights are stored under `data/models/` (not the repo root)
  so a slow/partial background download can't pollute the working
  directory or get committed.

### 4.2 Motion-detection fallback (`_infer_motion`)

`cv2.createBackgroundSubtractorMOG2` with a 20-frame warm-up window (MOG2
floods the very first frames with "this whole image is foreground" until
it has learned the background — returning detections during warm-up would
produce a false full-frame alert on every startup). After warm-up,
contours above an area threshold become `Detection(class_name="motion",
...)` entries, which flow through the exact same tracker/alert/storage
pipeline as YOLO detections.

### 4.3 Demo source reports its own ground truth

`DemoSource` procedurally draws a guard-house gate scene (sky gradient,
gate structure, a walking "person," a passing "car") with OpenCV
primitives. A real object detector will not reliably recognize hand-drawn
shapes as their COCO classes, so `DemoSource.simulated_detections()`
returns the exact bounding boxes it just drew, bypassing the detector
entirely. The Live Monitor loop checks `source.simulated_detections()`
first and only calls `detector.infer()` for real sources — this is the one
place the pipeline branches by source type, and it exists specifically so
the demo can exercise zones/tracking/alerting/analytics end-to-end without
ever claiming an AI result it didn't actually produce (the UI always
labels it "Simulated").

### 4.4 Why a custom centroid tracker instead of ByteTrack/DeepSORT

Dwell-time (loitering) measurement needs *a* stable ID per object across
frames — it doesn't need re-identification after long occlusion or
appearance embeddings. `CentroidTracker` (nearest-centroid greedy matching,
same-class constraint, configurable max distance/disappearance) is ~150
lines, has zero extra dependencies, and is fast enough for CPU real-time
use. If a future requirement needs robust re-ID across occlusion, this is
the seam to swap in a heavier tracker.

### 4.5 Alert cooldowns

Every alert type keys its cooldown differently on purpose:
- `intrusion:{zone}:{track_id or class}` — same object re-triggering in
  the same zone is suppressed, but a *different* object in the same zone
  still alerts.
- `loiter:{zone}:{track_id}` — per-track, so multiple loiterers in one
  zone each get their own alert.
- `threat:{class}:{zone}` and `crowd` (global) — coarser, since these are
  frame-level conditions rather than per-object.

### 4.6 Zone editor: why sliders + a coordinate table, not a canvas library

The original implementation used `streamlit-drawable-canvas` for
click-and-drag polygon drawing. It was replaced after discovering (via a
real browser test, not just code review) that the package — last released
in 2022 — calls a private Streamlit API
(`streamlit.elements.image.image_to_url`) that no longer exists in current
Streamlit, crashing the page outright. A Plotly click-to-place-vertex
alternative was also prototyped and rejected: clicking on a `go.Image`
trace doesn't reliably emit `on_select` point events in Streamlit's
current Plotly integration. The final design — **paired min/max sliders
for quick rectangular zones (with a live OpenCV-rendered preview on every
rerun) plus a `st.data_editor` table for arbitrary polygons** — uses only
native, actively maintained Streamlit/OpenCV/pandas functionality, is
fully interactive (the preview updates as you drag), and has no
third-party UI dependency to go stale again.

### 4.7 `st.audio` and duplicate element IDs

Streamlit assigns auto-generated element IDs from an element's type and
parameters; calling `st.audio` repeatedly with **identical** cached bytes
across loop iterations (one script run, many frames) collides as a
"duplicate element" and raises `StreamlitDuplicateElementId` — `st.audio`
has no `key` parameter to disambiguate with, unlike most other widgets.
The fix is to make each call's audio content trivially distinct: the beep
tone's frequency is nudged by a few Hz per alert
(`generate_beep_wav(freq=950 + counter % 30)`), which is inaudible as a
pitch difference but changes the underlying bytes enough to avoid the
collision.

### 4.8 ASCII-only text on video overlays

OpenCV's Hershey fonts (`cv2.putText`) only render ASCII — an em dash or
any other non-ASCII character (which a user could type into "Site name"
in Settings) renders as garbled `?` glyphs on the HUD. All text drawn onto
frames goes through `drawing._safe_text()`, which replaces non-ASCII
characters before rendering. (The Streamlit UI text itself is unaffected —
this only applies to pixels burned into the video frame.)

### 4.9 RTSP connection timeout

`cv2.VideoCapture()` against an unreachable RTSP URL has no short default
timeout — observed hangs of 30s+ before failing. `RTSPSource` and
`WebcamSource` pass `CAP_PROP_OPEN_TIMEOUT_MSEC` /
`CAP_PROP_READ_TIMEOUT_MSEC` (5000ms) via OpenCV's capture-params
constructor overload so a bad camera URL fails fast with a clear "could
not connect" message instead of freezing Start Monitoring.

## 5. Persistence

SQLite (`data/sentryvision.db`), two tables:

- **`alerts`** — one row per fired alert: timestamp, camera, type,
  severity, object class, confidence, zone, bbox, message, snapshot path,
  acknowledged flag.
- **`frame_stats`** — one row roughly per second of monitoring (not per
  frame, to keep the table small): total object count and a per-class
  count JSON blob, used to drive the Analytics timeline/class-distribution
  charts without replaying every frame.

`EventStore` wraps the connection with `check_same_thread=False` plus an
internal lock, since Streamlit can invoke callbacks from more than one
thread.

Zones (`data/zones.json`) and settings (`data/settings.json`) are flat
JSON files — human-readable, diffable, and easy to seed for a fresh
deployment without touching the UI.

## 6. Testing strategy

45 unit tests (`pytest`, `pythonpath = ["."]` — no package install step
needed) cover every backend module without requiring a camera, a model
download, or a browser:

- **`test_zones.py`** — point-in-polygon geometry, zone (de)serialization.
- **`test_tracker.py`** — ID continuity, ID separation by class/distance,
  disappearance cleanup, zone dwell-time accounting.
- **`test_alerts.py`** — each alert rule (intrusion/loitering/crowd/
  threat), cooldown suppression, armed/disarmed behavior.
- **`test_detector.py`** — the motion-detection fallback path (forced via
  an invalid model name), warm-up behavior, `infer(None)` safety.
- **`test_video_stream.py`** — `DemoSource` frame shape and simulated
  detection validity.
- **`test_db.py`** — alert/frame-stat logging, filtering, acknowledgment,
  retention purging.
- **`test_metrics.py`** — the pandas transforms behind every Analytics
  chart (this suite exists *because* `alerts_by_hour` originally shipped
  with a `reset_index()` column-naming bug that only manifested with real
  data — see the "Verification" section below).
- **`test_config.py`** / **`test_system.py`** — settings round-tripping
  and end-to-end component wiring.

### Verification beyond unit tests

Unit tests alone did not catch several real bugs (a third-party UI
dependency crash, a pandas API quirk, a Streamlit duplicate-element-ID
error, and font rendering) because they only manifest when the full app
actually runs in a browser. This release was verified by scripting a
real Chromium browser (Playwright) through every page and workflow —
starting/stopping monitoring against the demo feed, drawing and saving
zones, triggering and acknowledging real intrusion alerts, exporting the
event log, switching video sources (including deliberately broken
webcam/RTSP paths to confirm graceful, bounded-time error handling), and
saving/testing notification settings — while asserting zero browser
console/page errors at each step.

## 7. Extending the system

- **New alert rule**: add a branch in `AlertEngine.evaluate()`, following
  the existing cooldown-key pattern; no UI changes required unless you
  want a new Settings field for its threshold.
- **New detector backend**: implement the same `infer(frame) ->
  list[Detection]` contract as `ObjectDetector` and swap it into
  `SurveillanceSystem.build()`.
- **New notification channel**: add a `send_x(settings, alert) -> (bool,
  str)` function to `notifier.py` and call it from `dispatch()`.
- **New video source**: implement `FrameSource` (`read()`, `release()`,
  `is_connected`) in `video/stream.py`.
