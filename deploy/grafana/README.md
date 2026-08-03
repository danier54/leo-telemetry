# Grafana dashboard quickstart

## Start services

```bash
cd /workspaces/leo-telemetry
docker compose -f deploy/grafana/docker-compose.yml up -d
```

## Open Grafana

- URL: http://127.0.0.1:3000
- Username: admin
- Password: admin

## Add Prometheus data source

- Navigate to Connections -> Data sources -> Add new data source
- Choose Prometheus
- Set URL to http://prometheus:9090
- Click Save & test

## Import dashboards

The repository already contains Grafana dashboard JSON files you can import directly:

- [deploy/grafana/dashboard.json](dashboard.json) for a general overview
- [deploy/grafana/dashboards/overview.json](dashboards/overview.json) for a landing page
- [deploy/grafana/dashboards/oresat.json](dashboards/oresat.json) for ORESAT0.5
- [deploy/grafana/dashboards/cp16.json](dashboards/cp16.json) for SAL-E/CP16
- [deploy/grafana/dashboards/cape1.json](dashboards/cape1.json) for CAPE-1

### Import steps

1. Open Grafana at http://127.0.0.1:3000
2. Go to Dashboards -> New -> Import
3. Upload one of the JSON files above
4. Select the Prometheus data source and click Import

## Suggested queries

- Readings rate:
  ```promql
  sum(rate(leo_telemetry_readings_total[5m]))
  ```

- Metric values:
  ```promql
  leo_telemetry_metric_value
  ```

- Last received timestamps:
  ```promql
  leo_telemetry_last_received_timestamp_seconds
  ```

## Demo data

If you want the dashboard to show live values immediately, run:

```bash
cd /workspaces/leo-telemetry
python scripts/live_dashboard.py
```
