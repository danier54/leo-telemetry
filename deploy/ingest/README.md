# Ingest deployment

A Helm chart for the Data Ingest & Queue Management service: a
Redis-backed dedup queue plus a long-running Deployment that polls
SatNOGS and pushes new frames into it.

## Bringing it up via ArgoCD

```
kubectl apply -f ../argocd/ingest-application.yaml
```

ArgoCD auto-detects this as a Helm chart (via `Chart.yaml`) and
renders/syncs it using `values.yaml` automatically, keeping it in sync
(prune + self-heal) on every push to `main`.

## How deploys happen

CI (`.github/workflows/build-ingest.yml`) builds and pushes the image on
every merge to `main`, then writes the new commit SHA back into
`values.yaml`'s `image.tag` and pushes that commit too. ArgoCD picks up
the resulting diff and rolls out the new image automatically — no manual
`kubectl rollout restart` needed.

## One-time image visibility step

The CI workflow pushes to `ghcr.io/danier54/leo-telemetry-ingest`.
GitHub Container Registry packages default to **private** even when the
source repo is public, so after the first successful build, either:

- Go to the package's GitHub settings and change its visibility to
  **Public** (simplest, no cluster changes needed), or
- Create a pull secret and reference it from `templates/deployment.yaml`
  (`imagePullSecrets`, commented in that file):

  ```
  kubectl create secret docker-registry ghcr-pull-secret \
    --docker-server=ghcr.io \
    --docker-username=<your-github-username> \
    --docker-password=<a PAT with read:packages> \
    -n leo-telemetry
  ```

## Optional: SatNOGS API token

Anonymous SatNOGS API access works but is rate-limited more
aggressively. To use a token, create the secret the Deployment already
looks for (it's optional, so the pod runs fine without it):

```
kubectl create secret generic ingest-secrets \
  --from-literal=satnogs-api-token=<token> \
  -n leo-telemetry
```

## Required: Postgres credentials secret

Unlike the SatNOGS token, Postgres can't start without a password, so
this secret must exist **before** the chart is first synced (or the
`ingest-postgres` pod will stay stuck in `CreateContainerConfigError`).
Pick two passwords and create it once:

```
kubectl create secret generic ingest-postgres-secrets \
  --from-literal=app-password=<password for the ingest app user> \
  --from-literal=readonly-password=<password for the decode_readonly user> \
  -n leo-telemetry
```

## Postgres historical archive (contract for Signal Processing / decode)

In addition to the live Redis FIFO queue, every dedup'd raw frame is also
written to a Postgres database (`ingest-postgres` in the `leo-telemetry`
namespace) as a durable historical record -- see the "Data Storage
Architecture" section of the project plan for why this exists alongside
Prometheus. This is what Signal Processing/decode should read from if you
want to replay or re-process frames independent of the live queue.

**Schema** (database `leo_telemetry`, table `raw_frames`):

| column                 | type        | notes                                   |
|------------------------|-------------|------------------------------------------|
| `id`                   | bigserial   | primary key, monotonically increasing     |
| `norad_id`             | integer     |                                            |
| `observation_id`       | bigint      | SatNOGS observation id                    |
| `observer_station_id`  | bigint      | SatNOGS ground station id                 |
| `received_at`          | timestamptz |                                            |
| `raw_bytes`            | bytea       | raw frame bytes, pre-decode               |
| `dedup_key`            | text        | unique; same key used by the Redis queue  |
| `inserted_at`          | timestamptz | when the row was written                  |

This matches the `RawFrame` dataclass in `leo_telemetry/common/models.py`
field-for-field (minus `id`/`inserted_at`, which only exist in Postgres).

**Access**: you get a read-only `decode_readonly` role -- it can `SELECT`
from `raw_frames` (and any future table the ingest app creates) but
nothing else. From inside the cluster:

```
postgresql://decode_readonly:<password>@ingest-postgres.leo-telemetry.svc.cluster.local:5432/leo_telemetry
```

For local development, port-forward it to your machine instead:

```
kubectl -n leo-telemetry port-forward svc/ingest-postgres 5432:5432
```

then connect to `postgresql://decode_readonly:<password>@localhost:5432/leo_telemetry`.

Get the password with:

```
kubectl -n leo-telemetry get secret ingest-postgres-secrets \
  -o jsonpath='{.data.readonly-password}' | base64 -d
```

**Reading it from Python**: rather than hand-writing SQL, you can reuse
`leo_telemetry.common.storage.RawFrameStore` directly -- it's already
async (via `psycopg`) and returns `RawFrame` objects:

```python
from leo_telemetry.common.storage import RawFrameStore

store = await RawFrameStore.connect(
    "postgresql://decode_readonly:<password>@ingest-postgres.leo-telemetry.svc.cluster.local:5432/leo_telemetry"
)
page = await store.fetch_since(after_id=0, limit=500)  # oldest first
for stored in page:
    print(stored.id, stored.frame.norad_id, stored.frame.dedup_key)
```

Page through the table by passing the last `id` you saw back in as
`after_id` on the next call, so you don't have to re-read frames you've
already processed.
