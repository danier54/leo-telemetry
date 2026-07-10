# Ingest deployment

Kubernetes manifests for the Data Ingest & Queue Management service:
a Redis-backed dedup queue plus a long-running Deployment that polls
SatNOGS and pushes new frames into it.

## Bringing it up via ArgoCD

```
kubectl apply -f ../argocd/ingest-application.yaml
```

ArgoCD will create the `leo-telemetry` namespace and sync everything in
this directory (`namespace.yaml`, `redis.yaml`, `configmap.yaml`,
`deployment.yaml`) automatically, and keep it in sync (prune + self-heal)
on every push to `main`.

## One-time image visibility step

The CI workflow (`.github/workflows/build-ingest.yml`) pushes to
`ghcr.io/danier54/leo-telemetry-ingest`. GitHub Container Registry
packages default to **private** even when the source repo is public, so
after the first successful build, either:

- Go to the package's GitHub settings and change its visibility to
  **Public** (simplest, no cluster changes needed), or
- Create a pull secret and reference it from `deployment.yaml`
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
