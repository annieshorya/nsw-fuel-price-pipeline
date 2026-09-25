# NSW Fuel Price Data Pipeline

A two-stage data engineering project built for COMP5339 (University of Sydney) that
retrieves, cleans, and streams live fuel price data from the NSW Government's
FuelCheck API, then visualises it on a real-time map dashboard.

Team: Adnan Ali, Akarsh Kumar, Akshat Jain, Annie Shorya, Kevin Ninan Mathew.

## What it does

**Stage 1 — batch data pipeline** (`stage1-data-collection/`)
Authenticates against the FuelCheck API, retrieves station and price data,
integrates it with a supplementary petrol station dataset, cleans it, and
stores it for analysis.

**Stage 2 — real-time pipeline + dashboard** (`stage2-realtime-pipeline/`)
- `src/publisher.py` — polls the FuelCheck API on a loop, cleans each batch,
  and publishes it to an MQTT broker.
- `src/dashboard.py` — subscribes to the MQTT topic and renders an
  auto-refreshing Streamlit map dashboard of live fuel prices.
- `archive/` — earlier drafts kept for reference (`dashboard2.py`,
  `dashboard21.py`, `assignment2.py`, etc.). `src/` holds the current version.
- `sample-data/` — example output so the dashboard can be demoed without a
  live API key.

## Setup

```bash
pip install -r requirements.txt
cp stage2-realtime-pipeline/.env.example stage2-realtime-pipeline/.env
# fill in your own FuelCheck API credentials in .env
```

You'll also need a running MQTT broker (e.g. `mosquitto` locally, or point
`MQTT_BROKER` in `.env` at one you have access to).

Run the pipeline:

```bash
cd stage2-realtime-pipeline/src
python publisher.py          # terminal 1: fetch + publish
streamlit run dashboard.py   # terminal 2: view the live dashboard
```

## Reports

Full write-ups for both stages are in `docs/`.

## Known issues / before you rely on this again

- An earlier version of `publisher.py` had a real FuelCheck API key, secret,
  and Basic-auth header hardcoded in plain text. They've been replaced with
  environment variables (`.env.example`) — **treat the old credentials as
  compromised and regenerate them from the FuelCheck developer portal** before
  reusing this project.
- `stage2-realtime-pipeline/archive/` has six near-duplicate script versions
  from iterative development (`dashboard.py`/`dashboard2.py`/`dashboard21.py`/
  `dashboard_debug.py`, `assignment2.py`/`assignment21.py`). Worth deleting
  once you're confident `src/` has everything you need — that's what git
  history is for.
