# Cloud Run + Pub/Sub deployment

This deployment keeps GitHub's public webhook endpoint separate from the repository-scanning worker.

```text
GitHub
  -> public Cloud Run ingress
  -> Pub/Sub topic/subscription
  -> private Cloud Run worker
  -> GitHub Check Run
```

The ingress verifies the GitHub webhook signature, normalizes only the required event fields, publishes a small queue message, and returns before repository scanning begins.

The worker is not public. Pub/Sub invokes it with Cloud Run IAM authentication. A failed worker request returns a non-2xx response so Pub/Sub can redeliver it.

Pub/Sub delivery is at-least-once. CWB carries GitHub's `X-GitHub-Delivery` value into the queue and stores it as the GitHub Check Run `external_id`. If the same queued delivery is retried after its Check Run completed, the worker reuses that result instead of scanning and posting a duplicate Check again.

## Why this deployment

- Cloud Run can scale to zero when idle.
- Pub/Sub provides durable redelivery instead of an in-memory background task.
- No third-party Python runtime dependency is required.
- The GitHub App private key is mounted only into the worker.
- The webhook secret is mounted only into the ingress.
- The Manifest callback stores generated GitHub credentials directly in Secret Manager.

## Deploy

Run from Google Cloud Shell or another environment with the Google Cloud CLI:

```bash
git clone https://github.com/kohli217/codex-workspace-bootstrap.git
cd codex-workspace-bootstrap
chmod +x deploy/cloudrun/deploy.sh
./deploy/cloudrun/deploy.sh YOUR_GCP_PROJECT_ID
```

The script first fails fast when the Google Cloud CLI is missing, no account is active, the project cannot be accessed, or billing is known to be disabled. It then:

1. enables the required Google Cloud APIs;
2. creates dedicated ingress, worker, and Pub/Sub-invoker service accounts;
3. creates the Pub/Sub topic/subscription and Secret Manager entries;
4. grants least-privilege IAM bindings;
5. builds the container;
6. deploys a public ingress and private worker in `asia-northeast1` by default;
7. configures authenticated Pub/Sub push delivery;
8. prints a one-time GitHub App setup URL.

The setup URL keeps the bootstrap secret in the URL fragment (`#token=...`). Browser fragments are not sent in the HTTP request, so the bootstrap token is not included in Cloud Run's request URL. A small bootstrap page POSTs the token in the request body and the ingress moves the verified server-side value into a Secure/HttpOnly cookie before rendering the App Manifest form.

The bootstrap token expires one hour after it is issued. If the setup window expires before App registration is completed, create a fresh token without rebuilding or redeploying the services:

```bash
./deploy/cloudrun/rotate-setup-token.sh YOUR_GCP_PROJECT_ID
```

After GitHub redirects to the Manifest callback, the generated client ID, private key, and webhook secret are written directly to Secret Manager. They are never rendered back to the browser.

## Region

Override the default Tokyo region:

```bash
CWB_REGION=asia-northeast2 ./deploy/cloudrun/deploy.sh YOUR_GCP_PROJECT_ID
```

## Runtime limits

- GitHub webhook bodies are accepted up to GitHub's 25 MB webhook payload cap.
- Worker requests use a 600-second Cloud Run/Pub/Sub deadline.
- Worker container concurrency is fixed at 1 so multiple repository clones do not contend inside the same 512 MiB instance.
- The worker uses the existing hardened checkout and repository-only preflight path.

## Cost

Cloud Run and Pub/Sub are usage-based services with free tiers, but Google Cloud billing must still be enabled for the project. Review current Google Cloud pricing before production use.
