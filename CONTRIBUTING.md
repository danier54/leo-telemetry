# Contributing

## Branches & PRs

- Branch names: `<domain>/<short-description>`, e.g. `ingest/rate-limit-handling`,
  `decode/bit-destuffing`, `demux/oresat-spec`, `observability/prometheus-exporter`.
- Open a PR into `main`; get at least one teammate review before merging.
- Keep PRs scoped to one track's work where possible — the shared contracts
  in `leo_telemetry/common/models.py` are the exception and may need a
  second opinion since they affect every track.

## Shared contracts

If your change needs a new or different field on `RawFrame`, `DecodedFrame`,
`TelemetryReading`, or `TelemetryMetric`, loop in whoever owns the
downstream consumer before merging — those dataclasses are the interface
between domains and an API change could break the next stage.

## Tests

- Run `uv run pytest` before opening a PR.
- Each track has a matching `tests/test_<track>/` directory with
  placeholder tests marked `@pytest.mark.skip` — un-skip and fill them in
  as you implement the corresponding module.

## Environment

```
uv sync
```
