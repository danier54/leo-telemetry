# leo-telemetry

An end-to-end pipeline that ingests LEO CubeSat telemetry from the SatNOGS
public API, decodes AX.25 data-link frames, demultiplexes the payload into
typed physical measurements, and visualizes satellite health in Grafana.

## Structure

```
leo_telemetry/
  common/          shared data contracts (RawFrame, DecodedFrame, TelemetryReading)
                    and target satellite config
  ingest/          SatNOGS polling client + dedup queue
  decode/          AX.25 frame sync, bit-destuffing, CRC-16 validation
                    (+ afsk1200.py: audio demod for real off-air recordings)
  demux/           byte-offset -> physical unit mapping (per-satellite specs in demux/specs/)
  observability/   Prometheus exporter + Skyfield orbital tracking
  scoring/         composite "mission readiness score" (cross-cutting)
tests/             mirrors the package layout above
deploy/
  ingest/          k8s manifests for the ingest service (see deploy/ingest/README.md,
                    and deploy/ingest/KUBECTL_CHEATSHEET.md for day-to-day kubectl commands)
  argocd/          ArgoCD Application pointing at deploy/ingest
.github/workflows/ CI: builds and pushes the ingest image to ghcr.io on push to main
```

Data flows: `ingest -> RawFrame -> decode -> DecodedFrame -> demux -> TelemetryReading -> observability/scoring`.
The dataclasses in `leo_telemetry/common/models.py` are the interface
boundary between stages — read them before changing what one stage hands
to the next.

## Ownership

| Domain | Package |
|---|---|
| Data Ingest & Queue Management | `leo_telemetry/ingest` |
| Signal Processing & Protocol Decoding | `leo_telemetry/decode` |
| Telemetry Demultiplexing | `leo_telemetry/demux` |
| Observability & Visualization | `leo_telemetry/observability` |


## Setup

```
uv sync
```

## Running tests

```
uv run pytest
```
