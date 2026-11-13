# Smart Building Security Console

Context-aware multi-sensor event correlation for smart building physical security.
INSE 6680 · Systems Physical Security · Concordia University

A local prototype that ingests simulated access-control, camera, door-controller, door-contact, motion, and environmental messages, normalizes them into one event format, and correlates ordered sequences inside a time window and a security zone into composite incidents. The dashboard shows how dozens of standalone alerts collapse into a handful of incidents, each with a severity and an evidence timeline.

## Features

- **Live session.** Send individual sensor events from the Simulate tab on any device on the same network, such as a phone. The Overview polls every two seconds and the new events and incidents animate in.
- **Break a rule.** One button per rule plays its event sequence into the live session one event at a time, a few seconds apart, with a step-by-step progress view that ends when the incident is raised. Ideal for showing what a rule violation looks like as it unfolds.
- **Custom rules.** Create new correlation rules from the dashboard: title, severity, an ordered event sequence, window, and zone or after-hours constraints. Custom rules persist in `data/custom_rules.json`, apply to the live session immediately, and get their own "Break a rule" button.
- **Scenario replay.** Twelve reproducible scenarios cover authorized activity, equipment outages, sequence and timing boundaries, zone mismatches, and duplicate messages.
- **Correlation engine.** Configurable rules match ordered event kinds within a window, restricted to one zone, optionally limited to restricted areas or after-hours periods.
- **Evidence timelines.** Each incident lists the events that triggered it, with relative offsets and a window-progress bar.
- **Evaluation.** A fixed scenario suite reports detection rate, false-positive rate, a confusion matrix, and alert reduction versus a standalone-alert baseline.
- **Run history.** Every replay or saved live session is stored in SQLite with its full evidence and can be reopened. Stored runs can be wiped from the Simulate tab.
- **Design system.** Semantic colour tokens, light and dark themes, IBM Plex Sans for the interface and JetBrains Mono for identifiers and timestamps.

## Architecture

```
frontend/            React 19 + Vite + Tailwind v4 single-page dashboard
  src/App.jsx        Views: Overview, Simulate, Run history, Correlation rules, Evaluation
  src/styles.css     Design tokens, themes, and component classes
backend/
  security_console/
    main.py          FastAPI application and REST API
    models.py        Event, Rule, Incident, Run models (Pydantic)
    sensors.py       Zone map and raw-signal → event normalization
    correlation.py   Rule loading, de-duplication, sequence correlation
    simulation.py    Fixed scenarios, simulator, and evaluation metrics
    live.py          In-memory live session fed by the Simulate tab, plus rule playback
    rulebook.py      Built-in rules plus persisted custom rules
    storage.py       SQLite run store
    rules.json       Active correlation rules
  tests/             pytest suite for the API and the correlation engine
```

The backend serves the built frontend from `frontend/dist`, so one process hosts both the API and the dashboard.

## Run on Windows

Requires Python 3.11 or later and Node.js 20.19+ or 22.12+. From the project folder in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m uvicorn security_console.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open [the dashboard](http://127.0.0.1:8000/) or [the interactive API documentation](http://127.0.0.1:8000/docs). The database starts with one seeded demonstration run of camera and controller tampering.

For frontend development keep the backend running and use `npm.cmd --prefix frontend run dev`. Vite proxies `/api` requests to port 8000.

## Live demonstration from a phone

1. Start the backend bound to all interfaces instead of localhost:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn security_console.main:app --app-dir backend --host 0.0.0.0 --port 8000
   ```

2. Find the laptop's address on the shared Wi-Fi with `ipconfig` (the IPv4 address of the wireless adapter, for example `192.168.1.24`). Allow Python through Windows Firewall if prompted.
3. Keep the **Overview** open on the presentation screen with **Live session** selected.
4. On the phone, open `http://<laptop-address>:8000/#simulate`. Pick a zone and a sensor event and press **Send event**, or use the quick-send buttons. Each event appears on the Overview within two seconds, and a matching sequence raises an incident immediately.

A useful script: in the Server Room, send **Camera offline**, then **Controller unavailable**, then **Forced door opening**. The first two produce no incident on their own. The third completes the sequence and raises a critical incident with all three as evidence.

To demonstrate a rule violation without pressing buttons one at a time, use **Break a rule** on the Simulate or Correlation rules tab. Pick a zone, tap a rule, and its events are sent about a second apart while the progress panel shows each step. The incident appears on the Overview as the last event lands. After-hours rules played during staffed hours are stamped at 22:00 building time so they can match; the progress panel says so.

**Save session as run** stores the live session in Run history. **Clear live session** starts over. **Delete all saved runs** removes every stored run, including the seeded demonstration.

## Theme

The dashboard follows the system colour scheme by default. Use the **System / Light / Dark** switch at the bottom of the sidebar, or append `?theme=light` or `?theme=dark` to the URL, which is useful when projecting.

## REST API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness check |
| GET | `/api/scenarios` | Fixed scenarios with expected rules |
| GET | `/api/rules` | Active correlation rules, built-in and custom |
| POST | `/api/rules` | Create a custom rule (title, severity, sequence, window_seconds, restricted_only, after_hours_only) |
| DELETE | `/api/rules/{id}` | Delete a custom rule |
| GET | `/api/evaluation` | Scenario matrix and metrics |
| GET | `/api/runs` | Most recent saved runs (`limit` 1–100) |
| GET | `/api/runs/{id}` | One run with events and incidents |
| POST | `/api/runs` | Replay a scenario (`{"scenario_id": "tampering"}`) |
| DELETE | `/api/runs` | Delete every saved run |
| GET | `/api/live` | Live session state and version counter |
| GET | `/api/live/options` | Zones and sensor events available to the sender |
| POST | `/api/live/events` | Add one event (`{"location": "server", "system": "camera", "signal": "link_down"}`) |
| POST | `/api/live/play` | Play a rule's sequence into the live session step by step (`{"rule_id": "camera-door", "location": "server"}`) |
| POST | `/api/live/save` | Store the live session as a run |
| DELETE | `/api/live` | Clear the live session |

## Rules and assumptions

Built-in rules live in [rules.json](backend/security_console/rules.json); edit it and restart the backend, or set `SECURITY_RULES` to an alternate file. Custom rules created in the dashboard are stored beside the database in `data/custom_rules.json`. The defaults are prototype settings.

| Rule | Ordered evidence | Window | Severity |
| --- | --- | ---: | --- |
| Camera outage and forced entry | Camera offline → forced door | 120 s | High |
| Camera and controller tampering | Camera offline → controller offline → forced door | 120 s | Critical |
| Repeated denied access | Three distinct denials → forced door | 90 s | High |
| After-hours entry | Unverified door opening → motion | 60 s | Medium |

Default rules apply to restricted areas within a single zone. After-hours means outside 07:00–19:00 on weekdays, or any time on weekends, in Toronto. Events are normalized to UTC and must have strictly increasing times within a sequence. The window is inclusive. Event IDs are unique per run. Exact replays are discarded and conflicting payloads with the same ID are rejected.

Rules that share a final event produce one incident. Severity takes precedence, then sequence length, then rule ID. The incident keeps the union of matching evidence in time order. SQLite stores each run as a snapshot at `data/security.sqlite3`. Set `SECURITY_DB` to use another path.

## Evaluate and test

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
```

Open **Evaluation** in the dashboard or request `GET /api/evaluation`. Each of the 12 scenarios passes when its actual primary rules match the fixed expectation. Detection and false-positive rates use scenario-level incident presence. The standalone baseline counts one alert per outage, denial, forced or unverified opening, motion, or temperature warning. Alert reduction is the decrease from that baseline to the composite incident count. These figures characterize the fixed synthetic suite only.

## Scope

The simulator uses synthetic devices, a configured zone map, and reproducible batches. Correlation uses event type, location, restrictions, and time. The prototype runs locally and assumes trusted input. It is a course project, not a production security system.
