# Ingest deployment

A Helm chart for the Data Ingest & Queue Management service: a
Redis-backed dedup queue plus a long-running Deployment that polls
SatNOGS and pushes new frames into it.

## Bringing it up via ArgoCD

```
kubectl apply -f ../argocd/ingest-application.yaml
```

ArgoCD auto-detects this as a Helm chart (via `Chart.yaml`), creates the
`leo-telemetry` namespace, and renders/syncs it using `values.yaml`
automatically, keeping it in sync (prune + self-heal) on every push to
`main`.

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
