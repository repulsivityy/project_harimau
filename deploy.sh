#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
TARGET=${1:-all}
REGION="asia-southeast1" # Change if needed
BACKEND_SERVICE="harimau-backend"
FRONTEND_SERVICE="harimau-frontend"

echo "🐯 Deploying Project Harimau to GCP ($PROJECT_ID)..."

# 1. Enable Services
echo "Ensuring APIs are enabled..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com || true

# 2. Setup Secrets (GTI_API_KEY & WEBRISK_API_KEY)
SECRET_NAME="harimau-gti-api-key"
WEBRISK_SECRET_NAME="harimau-webrisk-api-key"
SERVICE_ACCOUNT_EMAIL="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com"

# Check if user wants to update secrets
if [ -n "$GTI_API_KEY" ]; then
    read -p "❓ Local GTI_API_KEY found. Update Secret Manager? [y/N] " response
    if [[ "$response" =~ ^[yY]$ ]]; then
        echo "🔄 Updating secret ($SECRET_NAME)..."
        if ! gcloud secrets describe $SECRET_NAME --quiet > /dev/null 2>&1; then
            printf "$GTI_API_KEY" | gcloud secrets create $SECRET_NAME --data-file=-
        else
            printf "$GTI_API_KEY" | gcloud secrets versions add $SECRET_NAME --data-file=-
        fi
        echo "✅ Secret updated."
    else
        echo "⏭️  Skipping secret update (using existing version)."
    fi
else
    echo "⚠️  GTI_API_KEY not set locally. Assuming secret exists..."
fi

if [ -n "$WEBRISK_API_KEY" ]; then
    read -p "❓ Local WEBRISK_API_KEY found. Update Secret Manager? [y/N] " response
    if [[ "$response" =~ ^[yY]$ ]]; then
        echo "🔄 Updating secret ($WEBRISK_SECRET_NAME)..."
        if ! gcloud secrets describe $WEBRISK_SECRET_NAME --quiet > /dev/null 2>&1; then
            printf "$WEBRISK_API_KEY" | gcloud secrets create $WEBRISK_SECRET_NAME --data-file=-
        else
            printf "$WEBRISK_API_KEY" | gcloud secrets versions add $WEBRISK_SECRET_NAME --data-file=-
        fi
        echo "✅ Secret updated."
    else
        echo "⏭️  Skipping secret update (using existing version)."
    fi
else
    echo "⚠️  WEBRISK_API_KEY not set locally. Assuming secret exists..."
fi

# Final check to ensure secret exists before deploying
if ! gcloud secrets describe $SECRET_NAME --quiet > /dev/null 2>&1; then
    echo "❌ Error: Secret '$SECRET_NAME' does not exist in Cloud and no local key provided."
    exit 1
fi
if ! gcloud secrets describe $WEBRISK_SECRET_NAME --quiet > /dev/null 2>&1; then
    echo "❌ Error: Secret '$WEBRISK_SECRET_NAME' does not exist in Cloud and no local key provided."
    exit 1
fi

# Grant Access to Cloud Run SA (Secret Manager + Vertex AI)
# Note: Check if binding exists to avoid redundant updates

# Secret Manager Access (GTI)
if ! gcloud secrets get-iam-policy $SECRET_NAME --format=json | grep -q "$SERVICE_ACCOUNT_EMAIL"; then
    echo "🔐 Granting Secret Access ($SECRET_NAME)..."
    gcloud secrets add-iam-policy-binding $SECRET_NAME \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" --quiet > /dev/null
else
    echo "✅ Secret Access ($SECRET_NAME) already granted."
fi

# Secret Manager Access (WebRisk)
if ! gcloud secrets get-iam-policy $WEBRISK_SECRET_NAME --format=json | grep -q "$SERVICE_ACCOUNT_EMAIL"; then
    echo "🔐 Granting Secret Access ($WEBRISK_SECRET_NAME)..."
    gcloud secrets add-iam-policy-binding $WEBRISK_SECRET_NAME \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" --quiet > /dev/null
else
    echo "✅ Secret Access ($WEBRISK_SECRET_NAME) already granted."
fi

# Vertex AI Access
if ! gcloud projects get-iam-policy $PROJECT_ID --format="json(bindings)" | grep -q "roles/aiplatform.user.*$SERVICE_ACCOUNT_EMAIL"; then
    echo "🤖 Granting Vertex AI Access..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/aiplatform.user" --condition=None --quiet > /dev/null
else
    echo "✅ Vertex AI Access already granted."
fi



# 4. Deploy Logic
if [[ "$TARGET" == "backend" || "$TARGET" == "all" ]]; then
    echo "🚀 Deploying Backend..."
    gcloud run deploy $BACKEND_SERVICE \
        --source . \
        --region $REGION \
        --allow-unauthenticated \
        --set-env-vars "LOG_LEVEL=DEBUG,MAX_DEPTH=2,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION}" \
        --set-secrets "VT_APIKEY=${SECRET_NAME}:latest,GTI_API_KEY=${SECRET_NAME}:latest,WEBRISK_API_KEY=${WEBRISK_SECRET_NAME}:latest" \
        --command "uvicorn" \
        --args "backend.main:app,--host,0.0.0.0,--port,8080" \
        --quiet
fi

# Always fetch Backend URL if deploying Frontend or needed
if [[ "$TARGET" == "all" || "$TARGET" == "frontend" ]]; then
     BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE --region $REGION --format 'value(status.url)' --quiet)
     echo "✅ Backend Live at: $BACKEND_URL"
fi

if [[ "$TARGET" == "frontend" || "$TARGET" == "all" ]]; then
    echo "🚀 Deploying Frontend..."
    gcloud builds submit --config deploy/cloudbuild_frontend.yaml . --quiet
    
    gcloud run deploy $FRONTEND_SERVICE \
        --image gcr.io/$PROJECT_ID/$FRONTEND_SERVICE \
        --region $REGION \
        --allow-unauthenticated \
        --set-env-vars BACKEND_URL=$BACKEND_URL \
        --port 8501 \
        --quiet
    
    FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE --region $REGION --format 'value(status.url)')
    echo "➡️  Frontend: $FRONTEND_URL"
fi

if [[ "$TARGET" == "backend" || "$TARGET" == "all" ]]; then
     echo "➡️  Backend:  $BACKEND_URL"
fi

echo "🎉 Deployment Complete!"