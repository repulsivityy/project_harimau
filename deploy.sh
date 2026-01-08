#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="asia-southeast1" # Change if needed
BACKEND_SERVICE="harimau-backend"
FRONTEND_SERVICE="harimau-frontend"

echo "🐯 Deploying Project Harimau to GCP ($PROJECT_ID)..."

# 1. Enable Services (First time only, safely skipped if enabled)
echo "Ensuring APIs are enabled..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com || true

# 2. Deploy Backend (Monolith)
echo "🚀 Deploying Backend..."
gcloud run deploy $BACKEND_SERVICE \
    --source . \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars LOG_LEVEL=INFO,MAX_DEPTH=2 \
    --command "uvicorn" \
    --args "backend.main:app,--host,0.0.0.0,--port,8080" \
    --quiet

# Capture Backend URL
BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE --region $REGION --format 'value(status.url)' --quiet)
echo "✅ Backend Live at: $BACKEND_URL"

# 3. Deploy Frontend (Streamlit)
echo "🚀 Deploying Frontend..."
# Note: Streamlit needs a separate build context or specific Dockerfile instructions.
# Since our root has the Backend Dockerfile, we need to point to app/Dockerfile.
# gcloud run deploy --source . uses the root Dockerfile by default.
# We will submit a Cloud Build to target the correct Dockerfile.

gcloud builds submit --config deploy/cloudbuild_frontend.yaml . --quiet

gcloud run deploy $FRONTEND_SERVICE \
    --image gcr.io/$PROJECT_ID/$FRONTEND_SERVICE \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars BACKEND_URL=$BACKEND_URL \
    --port 8501 \
    --quiet

FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE --region $REGION --format 'value(status.url)')

echo "🎉 Deployment Complete!"
echo "➡️  Frontend: $FRONTEND_URL"
echo "➡️  Backend:  $BACKEND_URL"
