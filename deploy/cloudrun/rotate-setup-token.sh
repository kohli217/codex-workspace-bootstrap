#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${CWB_REGION:-asia-northeast1}"
INGRESS_SERVICE="${CWB_INGRESS_SERVICE:-cwb-github-ingress}"
SETUP_TOKEN_SECRET="${CWB_SETUP_TOKEN_SECRET:-cwb-github-setup-token}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: ./deploy/cloudrun/rotate-setup-token.sh <gcp-project-id>" >&2
  exit 2
fi

gcloud config set project "${PROJECT_ID}" >/dev/null

if ! gcloud secrets describe "${SETUP_TOKEN_SECRET}" >/dev/null 2>&1; then
  echo "Setup-token secret does not exist. Run deploy.sh first." >&2
  exit 1
fi

INGRESS_URL="$(gcloud run services describe "${INGRESS_SERVICE}" \
  --region "${REGION}" \
  --format='value(status.url)')"

if [[ -z "${INGRESS_URL}" ]]; then
  echo "Could not resolve the Cloud Run ingress URL." >&2
  exit 1
fi

SETUP_TOKEN="$(python3 -c 'import secrets,time; print(f"v1.{int(time.time())}.{secrets.token_urlsafe(32)}")')"
printf '%s' "${SETUP_TOKEN}" | \
  gcloud secrets versions add "${SETUP_TOKEN_SECRET}" --data-file=- >/dev/null

echo "Fresh setup token created. It expires one hour after issuance."
echo "Open:"
echo "${INGRESS_URL}/setup/github#token=${SETUP_TOKEN}"
