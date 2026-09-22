#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${CWB_REGION:-asia-northeast1}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: ./deploy/cloudrun/deploy.sh <gcp-project-id>" >&2
  exit 2
fi

INGRESS_SERVICE="${CWB_INGRESS_SERVICE:-cwb-github-ingress}"
WORKER_SERVICE="${CWB_WORKER_SERVICE:-cwb-github-worker}"
TOPIC="${CWB_PUBSUB_TOPIC:-cwb-github-scans}"
SUBSCRIPTION="${CWB_PUBSUB_SUBSCRIPTION:-cwb-github-scans-worker}"
AR_REPOSITORY="${CWB_ARTIFACT_REPOSITORY:-cwb}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/github-app:latest"

INGRESS_SA_NAME="${CWB_INGRESS_SA:-cwb-github-ingress}"
WORKER_SA_NAME="${CWB_WORKER_SA:-cwb-github-worker}"
PUBSUB_SA_NAME="${CWB_PUBSUB_SA:-cwb-pubsub-invoker}"

CLIENT_ID_SECRET="${CWB_CLIENT_ID_SECRET:-cwb-github-client-id}"
PRIVATE_KEY_SECRET="${CWB_PRIVATE_KEY_SECRET:-cwb-github-private-key}"
WEBHOOK_SECRET="${CWB_WEBHOOK_SECRET:-cwb-github-webhook-secret}"
SETUP_TOKEN_SECRET="${CWB_SETUP_TOKEN_SECRET:-cwb-github-setup-token}"

gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Enabling Google Cloud APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

ensure_service_account() {
  local name="$1"
  if ! gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${name}" --display-name="${name}" >/dev/null
  fi
}

ensure_secret() {
  local secret="$1"
  if ! gcloud secrets describe "${secret}" >/dev/null 2>&1; then
    gcloud secrets create "${secret}" --replication-policy=automatic >/dev/null
  fi
}

ensure_secret_version() {
  local secret="$1"
  local value="$2"
  if [[ "$(gcloud secrets versions list "${secret}" --filter='state:ENABLED' --format='value(name)' | head -n 1)" == "" ]]; then
    printf '%s' "${value}" | gcloud secrets versions add "${secret}" --data-file=- >/dev/null
  fi
}

ensure_service_account "${INGRESS_SA_NAME}"
ensure_service_account "${WORKER_SA_NAME}"
ensure_service_account "${PUBSUB_SA_NAME}"

INGRESS_SA="${INGRESS_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_SA="${WORKER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
PUBSUB_SA="${PUBSUB_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
PUBSUB_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPOSITORY}" \
    --repository-format=docker \
    --location="${REGION}" >/dev/null
fi

if ! gcloud pubsub topics describe "${TOPIC}" >/dev/null 2>&1; then
  gcloud pubsub topics create "${TOPIC}" >/dev/null
fi

for secret in "${CLIENT_ID_SECRET}" "${PRIVATE_KEY_SECRET}" "${WEBHOOK_SECRET}" "${SETUP_TOKEN_SECRET}"; do
  ensure_secret "${secret}"
done

# Placeholder versions let Cloud Run mount :latest before the GitHub Manifest callback
# writes the real App credentials. No GitHub event can authenticate against these values.
ensure_secret_version "${CLIENT_ID_SECRET}" "UNCONFIGURED"
ensure_secret_version "${PRIVATE_KEY_SECRET}" "UNCONFIGURED"
ensure_secret_version "${WEBHOOK_SECRET}" "UNCONFIGURED"

SETUP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s' "${SETUP_TOKEN}" | gcloud secrets versions add "${SETUP_TOKEN_SECRET}" --data-file=- >/dev/null

echo "Configuring least-privilege IAM..."
gcloud pubsub topics add-iam-policy-binding "${TOPIC}" \
  --member="serviceAccount:${INGRESS_SA}" \
  --role="roles/pubsub.publisher" >/dev/null

for secret in "${CLIENT_ID_SECRET}" "${PRIVATE_KEY_SECRET}" "${WEBHOOK_SECRET}"; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${INGRESS_SA}" \
    --role="roles/secretmanager.secretVersionAdder" >/dev/null
done

for secret in "${SETUP_TOKEN_SECRET}" "${WEBHOOK_SECRET}"; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${INGRESS_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
done

for secret in "${CLIENT_ID_SECRET}" "${PRIVATE_KEY_SECRET}"; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${WORKER_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
done

echo "Building container..."
gcloud builds submit --tag "${IMAGE}" .

echo "Deploying private worker..."
gcloud run deploy "${WORKER_SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --service-account "${WORKER_SA}" \
  --no-allow-unauthenticated \
  --set-env-vars "CWB_GITHUB_APP_MODE=worker" \
  --set-secrets "/var/run/secrets/cwb/client-id=${CLIENT_ID_SECRET}:latest,/var/run/secrets/cwb/private-key=${PRIVATE_KEY_SECRET}:latest" \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 600 >/dev/null

WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" --region "${REGION}" --format='value(status.url)')"

echo "Deploying public webhook ingress..."
gcloud run deploy "${INGRESS_SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --service-account "${INGRESS_SA}" \
  --allow-unauthenticated \
  --set-env-vars "CWB_GITHUB_APP_MODE=ingress,CWB_GCP_PROJECT=${PROJECT_ID},CWB_PUBSUB_TOPIC=${TOPIC},CWB_GITHUB_CLIENT_ID_SECRET=${CLIENT_ID_SECRET},CWB_GITHUB_PRIVATE_KEY_SECRET=${PRIVATE_KEY_SECRET},CWB_GITHUB_WEBHOOK_SECRET=${WEBHOOK_SECRET}" \
  --set-secrets "/var/run/secrets/cwb/setup-token=${SETUP_TOKEN_SECRET}:latest,/var/run/secrets/cwb/webhook-secret=${WEBHOOK_SECRET}:latest" \
  --cpu 1 \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 30 >/dev/null

INGRESS_URL="$(gcloud run services describe "${INGRESS_SERVICE}" --region "${REGION}" --format='value(status.url)')"

# The App Manifest needs the final HTTPS service URL.
gcloud run services update "${INGRESS_SERVICE}" \
  --region "${REGION}" \
  --update-env-vars "CWB_PUBLIC_BASE_URL=${INGRESS_URL}" >/dev/null

echo "Authorizing Pub/Sub to invoke only the private worker..."
gcloud run services add-iam-policy-binding "${WORKER_SERVICE}" \
  --region "${REGION}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/run.invoker" >/dev/null

gcloud iam service-accounts add-iam-policy-binding "${PUBSUB_SA}" \
  --member="serviceAccount:${PUBSUB_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator" >/dev/null

PUSH_ENDPOINT="${WORKER_URL}/pubsub/github-scan"
if gcloud pubsub subscriptions describe "${SUBSCRIPTION}" >/dev/null 2>&1; then
  gcloud pubsub subscriptions update "${SUBSCRIPTION}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --push-auth-service-account="${PUBSUB_SA}" \
    --ack-deadline=600 \
    --min-retry-delay=10s \
    --max-retry-delay=600s >/dev/null
else
  gcloud pubsub subscriptions create "${SUBSCRIPTION}" \
    --topic="${TOPIC}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --push-auth-service-account="${PUBSUB_SA}" \
    --ack-deadline=600 \
    --min-retry-delay=10s \
    --max-retry-delay=600s >/dev/null
fi

echo
echo "CWB GitHub App deployment is ready."
echo "Ingress: ${INGRESS_URL}"
echo "Worker:  ${WORKER_URL}"
echo
echo "Open this one-time setup URL in your browser:"
echo "${INGRESS_URL}/setup/github#token=${SETUP_TOKEN}"
echo
echo "After the GitHub App is created, install it on one test repository."
