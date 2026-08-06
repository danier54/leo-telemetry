# leo-telemetry

An end-to-end pipeline that ingests LEO satellite telemetry from the SatNOGS
public API, decodes the downlink (AX.25 data-link frames, CW beacons, APRS),
demultiplexes payloads into typed physical measurements, and visualizes fleet
health in Grafana.

Live dashboard: https://dell-node2.tail34280b.ts.net/d/leo-overview
(read-only, no login needed).

## Structure

```
leo_telemetry/
  common/          shared data contracts (RawFrame, DecodedFrame, TelemetryReading)
                    and target satellite config
  ingest/          SatNOGS polling client + dedup queue + Postgres raw-frame archive
  decode/          AX.25 frame sync, bit-destuffing, CRC-16 validation
                    (+ cw.py: CW/Morse beacon validation for non-AX.25 satellites,
                     + afsk1200.py: audio demod for real off-air recordings)
  demux/           payload -> physical unit mapping (per-satellite specs in demux/specs/)
  observability/   Prometheus registry/exporter, Skyfield orbital tracking
                    (position + velocity), per-satellite last-reading persistence
  scoring/         composite "mission readiness score" (cross-cutting)
tests/             mirrors the package layout above; golden tests use real
                    frames captured from SatNOGS
deploy/
  ingest/          k8s manifests for the ingest service (see deploy/ingest/README.md,
                    and deploy/ingest/KUBECTL_CHEATSHEET.md for day-to-day kubectl commands)
  decode/, demux/, observability/
                   Helm charts for the other pipeline services
  prometheus/      Prometheus backend (15s scrape of the exporter, 30d retention)
  grafana/         Grafana provisioned from git: datasources (Prometheus +
                    read-only Postgres archive) and dashboards/ (overview,
                    per-satellite drill-down)
  argocd/          one ArgoCD Application per chart above
  rbac/            teammate cluster access
.github/workflows/ CI: runs pytest, builds the shared service image, pushes to
                    ghcr.io, and pins every chart's image tag on push to main
```

Data flows: `ingest -> RawFrame -> decode -> DecodedFrame -> demux -> TelemetryReading -> observability/scoring`.
The dataclasses in `leo_telemetry/common/models.py` are the interface
boundary between stages — read them before changing what one stage hands
to the next.

## Target satellites

| Satellite | NORAD | Downlink | Demux spec |
|---|---|---|---|
| ORESAT0.5 | 60525 | 9600bps FSK AX.25 | binary struct offsets |
| SAL-E/CP16 | 68458 | 9600bps FSK AX.25 | binary struct offsets |
| CAPE-1 | 31130 | CW (Morse) beacon | K5USL ASCII-hex beacon (decode/cw.py validates structure; current captures are noise) |
| SONATE-2 | 59112 | 9600bps GMSK AX.25 | CCSDS transfer frame, APID 100 housekeeping with published calibrations |
| ISS (ARISS) | 25544 | AFSK1200 APRS | APRS information field: frame classification, station positions, telemetry channels |

## Observability

The observability service drains demuxed readings into a Prometheus
registry (`/metrics` on port 8000), tracks live satellite positions and
velocities from Celestrak TLEs via Skyfield, reports the depth of every
stage-to-stage Redis queue, and persists each satellite's latest reading
in Redis so pod restarts do not blank the dashboard. Gauges are
monotonic in frame time, so out-of-order batches cannot regress them.

Grafana is provisioned entirely from git: the overview dashboard (live
position map with 6h ground tracks, orbital state, altitude, readiness
scores, telemetry history from both Prometheus and the Postgres
archive, pipeline queue depths) and a templated per-satellite
drill-down. The public URL is served through a Tailscale Funnel on the
cluster host; anonymous visitors are read-only viewers.

## Deploys

CI and ArgoCD automate everything: a merge to main that touches code
runs the tests, builds and pushes the image, and pins every chart's
image tag; ArgoCD syncs the charts into the cluster. Registering a new
chart is a one-time `kubectl apply -f deploy/argocd/<app>.yaml`.

## Setup

```
uv sync
```

## Running tests

```
uv run pytest
```
