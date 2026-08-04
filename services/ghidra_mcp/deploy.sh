#!/bin/bash
# =============================================================================
# Ghidra MCP Service — Deployment Script for Cloud Run
# =============================================================================
# USAGE:
#   ./deploy.sh
#
# REQUIRES:
#   - gcloud CLI authenticated and project set (gcloud config set project <PROJECT_ID>)
#   - Optional env var: GHIDRA_MCP_API_KEY (will prompt or generate if unset)
# =============================================================================
set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-southeast1"
SERVICE_NAME="ghidra-mcp"
IMAGE_NAME="asia-southeast1-docker.pkg.dev/${PROJECT_ID}/harimau/ghidra-mcp:latest"

GHIDRA_SECRET_NAME="ghidra-mcp-api-key"
GTI_SECRET_NAME="harimau-gti-api-key"

echo "=========================================================="
echo "🛡️  Deploying Ghidra MCP Reverse Engineering Service"
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"
echo "   Service: $SERVICE_NAME"
echo "=========================================================="

# 1. Ensure Secret Manager secret exists for GHIDRA_MCP_API_KEY
echo "🔐 Checking Secret Manager for $GHIDRA_SECRET_NAME..."
if ! gcloud secrets describe $GHIDRA_SECRET_NAME --quiet > /dev/null 2>&1; then
    echo "🆕 Secret '$GHIDRA_SECRET_NAME' not found."
    if [ -z "$GHIDRA_MCP_API_KEY" ]; then
        GHIDRA_MCP_API_KEY=$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c 32)
        echo "✨ Generated secure API Key: $GHIDRA_MCP_API_KEY"
        echo "⚠️  SAVE THIS SECURELY — you will need it for Harimau's backend!"
    fi
    printf "$GHIDRA_MCP_API_KEY" | gcloud secrets create $GHIDRA_SECRET_NAME --data-file=- --quiet
    echo "✅ Created secret $GHIDRA_SECRET_NAME."
else
    echo "✅ Existing secret $GHIDRA_SECRET_NAME found."
fi

# 2. Build Container Image via Cloud Build
echo "🏗️  Building Docker Image in Cloud Build..."
gcloud builds submit --tag $IMAGE_NAME . --quiet

# 3. Deploy Cloud Run Service
echo "🚀 Deploying $SERVICE_NAME to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --allow-unauthenticated \
    --memory="4096Mi" \
    --cpu="2" \
    --no-cpu-throttling \
    --timeout="300" \
    --concurrency="4" \
    --set-secrets "GHIDRA_MCP_API_KEY=${GHIDRA_SECRET_NAME}:latest,GTI_API_KEY=${GTI_SECRET_NAME}:latest,VT_API_KEY=${GTI_SECRET_NAME}:latest" \
    --quiet

# 4. Fetch and display deployed URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)' --quiet)
echo "=========================================================="
echo "✅ Ghidra MCP Service Deployed Successfully!"
echo "   Service URL: $SERVICE_URL"
echo "   MCP Endpoint: $SERVICE_URL/mcp"
echo "   Sample Loader: $SERVICE_URL/sample/download"
echo "=========================================================="
