# kubectl cheatsheet

Day-to-day commands for looking at the live ingest pipeline. Everything
below assumes you already have `kubectl` access to the cluster (Tailscale
+ kubeconfig -- ask Eric if you don't have this yet).

## Pod / service health

```
kubectl -n leo-telemetry get pods -o wide
```
Should show `ingest`, `ingest-redis`, and `ingest-postgres` all `Running`
with `0` (or a low) restart count.

```
kubectl -n leo-telemetry describe pod <pod-name>
```
Use when a pod isn't `Running` -- the `Events` section at the bottom
usually explains why (image pull failure, missing secret, etc.).

```
kubectl -n leo-telemetry rollout status deployment/ingest
```
Waits for a deployment's rollout to finish; useful right after a merge to
confirm the new image actually came up.

## Logs

```
kubectl -n leo-telemetry logs deploy/ingest --tail=50
kubectl -n leo-telemetry logs deploy/ingest --tail=50 -f     # follow live
```
Shows the poll loop: SatNOGS requests, HTTP status, and a
`Polled N frame(s), M new after dedup` line per cycle. Exceptions from a
failed poll or a failed Postgres write also show up here (poll failures
and Postgres write failures are both logged and swallowed, so the pod
keeps running -- check here first if data looks like it stopped flowing).

```
kubectl -n leo-telemetry logs deploy/ingest --previous
```
Logs from the *last* container instance, if the current one just
restarted and you want to see what killed it.

## Redis queue

```
kubectl -n leo-telemetry exec deploy/ingest-redis -- redis-cli LLEN leo_telemetry:ingest:queue
```
Current queue depth (number of deduped frames waiting for decode).

```
kubectl -n leo-telemetry exec deploy/ingest-redis -- redis-cli LLEN leo_telemetry:ingest:audio:queue
```
Same, for the ISS audio-observation queue (metadata for raw off-air
recordings, polled from SatNOGS Network -- see
`leo_telemetry/ingest/audio_client.py`).

```
kubectl -n leo-telemetry exec deploy/ingest-redis -- redis-cli SCARD leo_telemetry:ingest:seen
kubectl -n leo-telemetry exec deploy/ingest-redis -- redis-cli SCARD leo_telemetry:ingest:audio:seen
```
Size of the dedup "seen" sets. These grow while the queues stay short:
a frame the pipeline has already seen is skipped, so seen-set size >>
queue depth is normal and healthy.

```
kubectl -n leo-telemetry exec deploy/ingest -- python -c "
import pickle, redis
r = redis.Redis(host='ingest-redis')
for raw in r.lrange('leo_telemetry:ingest:queue', 0, 4):
    f = pickle.loads(raw)
    print(f.dedup_key, f.received_at, f'{len(f.raw_bytes)} bytes')
"
```
Human-readable peek at the first 5 queued frames. Queue entries are
pickled dataclasses, so plain `redis-cli LRANGE` prints gibberish -- this
runs inside the ingest pod, which has the code to unpickle them.

```
kubectl -n leo-telemetry exec deploy/ingest -- python -c "
import pickle, redis
r = redis.Redis(host='ingest-redis')
for raw in r.lrange('leo_telemetry:ingest:audio:queue', 0, 4):
    o = pickle.loads(raw)
    print(o.observation_id, o.observed_at, o.payload_url)
"
```
Same, for the audio queue. The printed `payload_url` is a direct link to
the actual `.ogg` recording -- paste it into a browser (or `curl -O` it)
to listen to / download the raw off-air audio.

## Postgres historical archive

See `README.md` in this directory for the full schema and the
`decode_readonly` access contract. Quick health checks:

```
kubectl -n leo-telemetry port-forward svc/ingest-postgres 5432:5432
```
Forwards Postgres to `localhost:5432` so you can connect with `psql` or
any Postgres client from your own machine. Leave this running in a
separate terminal; `Ctrl+C` to stop.

```
APP_PW=$(kubectl -n leo-telemetry get secret ingest-postgres-secrets -o jsonpath='{.data.app-password}' | base64 -d)
kubectl -n leo-telemetry exec deploy/ingest-postgres -- env PGPASSWORD="$APP_PW" \
  psql -U ingest -d leo_telemetry -c "SELECT norad_id, count(*) FROM raw_frames GROUP BY norad_id;"
```
Row counts per satellite, run directly inside the pod (no port-forward
needed).

```
kubectl -n leo-telemetry exec deploy/ingest-postgres -- env PGPASSWORD="$APP_PW" \
  psql -U ingest -d leo_telemetry -c "SELECT norad_id, observation_id, received_at, encode(raw_bytes, 'hex') AS frame_hex FROM raw_frames ORDER BY received_at DESC LIMIT 5;"
```
The 5 most recent frames with their raw payload as hex -- the same bytes
decode gets off the Redis queue, so this is the quickest way to eyeball
real frame data.

```
kubectl -n leo-telemetry exec -it deploy/ingest-postgres -- env PGPASSWORD="$APP_PW" \
  psql -U ingest -d leo_telemetry
```
Interactive psql session inside the pod for ad-hoc queries. `\d
raw_frames` shows the schema; `\q` exits. (Decode-track folks: use the
`decode_readonly` user/password instead -- see the Secrets section.)

## ArgoCD

```
kubectl -n argocd get application leo-telemetry-ingest -o jsonpath='{.status.sync.status} / {.status.health.status} / {.status.sync.revision}{"\n"}'
```
One-line sync/health/revision summary. Should read `Synced / Healthy /
<commit sha>`, where the sha matches the latest commit on `main`.

```
kubectl -n argocd annotate application leo-telemetry-ingest argocd.argoproj.io/refresh=hard --overwrite
```
Forces ArgoCD to re-check the repo immediately instead of waiting for its
normal poll interval. Useful right after a merge if you don't want to
wait ~3 minutes to see the new revision picked up.

## Secrets

```
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```
ArgoCD admin password (only needed once, the first time you log in).

```
kubectl -n leo-telemetry get secret ingest-postgres-secrets -o jsonpath='{.data.readonly-password}' | base64 -d
```
The `decode_readonly` Postgres password (swap `readonly-password` for
`app-password` to get the app's own credential instead).

## Troubleshooting

```
kubectl -n leo-telemetry rollout restart deployment/ingest
```
Manually restart the pod (e.g. to pick up a changed secret -- Kubernetes
doesn't auto-restart pods just because a referenced Secret's contents
changed).

```
kubectl -n leo-telemetry get events --sort-by=.lastTimestamp
```
Recent cluster events across the whole namespace, newest last -- good
first stop when something looks wrong and you don't know which resource
to blame yet.
