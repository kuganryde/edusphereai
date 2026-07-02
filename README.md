# 🛡️ SentryVision AI

An AI-powered CCTV surveillance and analysis platform for **guard houses and
sentry posts** — built entirely in Python. Real-time computer-vision object
detection (YOLOv8), configurable restricted zones, intrusion/loitering/crowd
alerts, an event log with snapshots, and an analytics dashboard, all behind
a single Streamlit app.

- **Product requirements:** [`PRD.md`](PRD.md)
- **Technical architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Features

- 🎥 **Live Monitor** — annotated video feed (bounding boxes, zone overlays,
  HUD) with a live alert feed and FPS/object-count stats.
- 🤖 **AI object detection** via Ultralytics YOLOv8, with automatic,
  transparent fallback to OpenCV motion detection if the model can't be
  loaded (no network on first run, etc.) — the app never refuses to run.
- 🗺️ **Zone Editor** — draw restricted or watch zones over a live snapshot
  with an interactive slider tool (live preview) or a precise-coordinates
  table for arbitrary polygons.
- 🚨 **Alerting** — intrusion, loitering (dwell time), crowding, and
  flagged-object rules, each cooldown-gated to avoid alert spam; optional
  arm/disarm schedule; sound, webhook (Slack/Discord/generic JSON), and
  email notifications.
- 📋 **Event Log** — searchable, filterable alert history with saved
  snapshots, acknowledgment, and CSV export.
- 📊 **Analytics** — activity trends, detections by class, alerts by hour
  and by zone, severity breakdown.
- ⚙️ **Settings** — everything above is configurable from the UI and
  persisted to disk; no config file editing required.
- 📡 **Any video source** — local webcam, RTSP/IP camera, an uploaded video
  file, or a built-in simulated demo scene that needs no camera at all.

## Quickstart

Prerequisite: install [`uv`](https://docs.astral.sh/uv/) if you don't
already have it:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

1. Sync dependencies:

   ```
   uv sync
   ```

2. Run the app:

   ```
   uv run streamlit run streamlit_app.py
   ```

3. Open the app in your browser, go to **Live Monitor**, and click
   **▶ Start Monitoring** — the **Demo Scene** source works immediately
   with no camera, model download, or configuration, so you can exercise
   zones, alerts, the event log, and analytics right away.

To point it at a real camera instead, open **Live Monitor → Video Source**
and switch to **Local Webcam**, **IP Camera / RTSP**, or upload a video
file.

## Lightweight / CPU-only install

The default install pulls PyTorch's standard PyPI wheel, which bundles CUDA
runtime libraries even on machines with no GPU (~5GB). On a CPU-only guard
house workstation or a small cloud instance, install the CPU-only PyTorch
build instead — same code, a few hundred MB instead of several gigabytes:

```
uv sync
uv pip install torch --index-url https://download.pytorch.org/whl/cpu --reinstall
```

## Running with Docker

A multi-stage `Dockerfile` is included (CPU-only PyTorch baked in, runs as a
non-root user, persists data via a volume):

```
docker build -t sentryvision-ai .
docker run -p 8501:8501 -v sentryvision-data:/app/data sentryvision-ai
```

Open `http://localhost:8501`. The `-v sentryvision-data:/app/data` volume
persists the SQLite DB, zones, settings, snapshots, and downloaded model
weights across container restarts — omit it for a fully ephemeral container.

This is *not* a good fit for Vercel or other serverless platforms: Streamlit
needs a persistent server process with a long-lived WebSocket connection,
which serverless functions don't provide. Use a container host that runs
persistent services instead — Render, Railway, Fly.io, a VPS, or Streamlit
Community Cloud (which doesn't need Docker at all — it deploys straight from
this GitHub repo).

## Running tests

```
uv run pytest
```

45 unit tests cover the detection/tracking/alerting/storage/analytics
backend without needing a camera, a model download, or a browser — see
`docs/ARCHITECTURE.md` for what's covered and how the app was additionally
verified end-to-end in a real browser.

## Project layout

```
streamlit_app.py     Entry point (page config + navigation)
app_state.py          Streamlit session/resource glue
pages/                Live Monitor, Zone Editor, Event Log, Analytics, Settings
surveillance/          Framework-agnostic backend (detection, tracking, alerts,
                       storage, analytics, video sources) — see docs/ARCHITECTURE.md
tests/                 Unit tests for the surveillance/ package
data/                  Runtime data: SQLite DB, zones, settings, snapshots (gitignored)
```

## Known limitations

- No firearm detection out of the box (stock COCO has no gun class — see
  PRD §9 for details and the roadmap).
- Single camera per running instance; multi-camera dashboards are on the
  roadmap.
- First run needs network access to download YOLOv8 weights; without it,
  the app automatically runs in motion-detection fallback mode instead of
  failing to start.

## License

See [`LICENSE`](LICENSE).
