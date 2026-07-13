# Ingest deployment

A Helm chart for the Data Ingest & Queue Management service: a
Redis-backed dedup queue plus a long-running Deployment that polls
SatNOGS and pushes new frames into it.

For day-to-day commands to check on the running pipeline (pod health,
logs, queue depth, Postgres row counts, ArgoCD sync status), see
[`KUBECTL_CHEATSHEET.md`](./KUBECTL_CHEATSHEET.md).

## Next steps for Signal Processing / decode (Jordan)

**Your primary input is the Redis queue, not Postgres.** Ingest pushes
every deduped `RawFrame` onto a Redis FIFO as its normal, real-time
hand-off to decode -- this is the "Ingest -> Signal Processing" contract
from the project plan's dependencies section, and it's already stable and
running live.

1. Consume frames with `leo_telemetry.ingest.redis_dedup.RedisDedupQueue`:
   ```python
   from redis.asyncio import Redis
   from leo_telemetry.ingest.redis_dedup import RedisDedupQueue

   queue = RedisDedupQueue(Redis.from_url("redis://ingest-redis:6379/0"))  # in-cluster
   frame = await queue.pop()  # RawFrame | None, oldest first
   ```
   For local development, port-forward first (see
   [`KUBECTL_CHEATSHEET.md`](./KUBECTL_CHEATSHEET.md#redis-queue)) and
   point `Redis.from_url` at `redis://localhost:6379/0` instead.
2. `RawFrame` (the type you'll get back) is defined in
   `leo_telemetry/common/models.py` -- read its docstring before writing
   against it, since it's the interface boundary between our two tracks.
3. Your own package already has a stubbed-out entry point to build
   against: `leo_telemetry/decode/ax25.py`'s `decode_frame(raw: RawFrame)
   -> DecodedFrame | None` calls into `frame_sync.py` (frame boundary
   detection + bit-destuffing) and `crc16.py` (FCS validation), both
   currently `raise NotImplementedError`. Your output type, `DecodedFrame`,
   is also in `common/models.py` and is what gets handed to Taurean's demux
   track next.
4. Tracked as issues
   [#13](https://github.com/danier54/leo-telemetry/issues/13),
   [#14](https://github.com/danier54/leo-telemetry/issues/14),
   [#15](https://github.com/danier54/leo-telemetry/issues/15), and
   [#16](https://github.com/danier54/leo-telemetry/issues/16) on the
   [project board](https://github.com/users/danier54/projects/5).

**Postgres is a secondary, optional replay archive** -- see "Postgres
historical archive" below. Use it only if you want to re-run your decoder
against frames that already scrolled past on the live queue (e.g. for
testing against real historical data); it is not part of the normal
ingest -> decode pipeline path, which is why access to it is read-only.

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

## Postgres historical archive (optional replay access for Signal Processing / decode)

In addition to the live Redis FIFO queue, every dedup'd raw frame is also
written to a Postgres database (`ingest-postgres` in the `leo-telemetry`
namespace) as a durable historical record -- see the "Data Storage
Architecture" section of the project plan for why this exists alongside
Prometheus. This is *not* the primary ingest -> decode hand-off (that's
the Redis queue, see "Next steps for Signal Processing / decode" above);
it's here for replaying or re-processing frames independent of the live
queue, which is also why decode's access to it is read-only.

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
