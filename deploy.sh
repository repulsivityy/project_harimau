#!/bin/bash
# =============================================================================
# Project Harimau — Deployment Script
# =============================================================================
#
# USAGE:
#   ./deploy.sh [backend|frontend|all]
#
#   backend   — Deploy backend Cloud Run service only
#   frontend  — Deploy frontend Cloud Run service only
#   all       — Deploy both (default)
#
# REQUIRED ENV VARS (export before running):
#   GTI_API_KEY        Google Threat Intelligence API key
#                      Saved to Secret Manager as 'harimau-gti-api-key'
#
#   WEBRISK_API_KEY    Google Web Risk API key
#                      Saved to Secret Manager as 'harimau-webrisk-api-key'
#
# OPTIONAL ENV VARS:
#   DETECTION_AGENT_URL   A2A endpoint of the detection agent Cloud Run service.
#                         When set, backend is deployed with DETECTION_AGENT_ENABLED=true
#                         so completed investigations are forwarded to the detection agent.
#                         When unset, DETECTION_AGENT_ENABLED=false (default — no forwarding).
#
#                         Example:
#                           export DETECTION_AGENT_URL=https://detection-agent-<PROJECT_ID>.asia-southeast1.run.app
#                           ./deploy.sh backend
#
#                         To toggle without redeploying:
#                           gcloud run services update harimau-backend \
#                             --set-env-vars DETECTION_AGENT_ENABLED=true,DETECTION_AGENT_URL=https://...
#
# NOTES:
#   - Requires gcloud CLI authenticated and project set (gcloud config set project <PROJECT_ID>)
#   - Region defaults to asia-southeast1. Change REGION below if needed.
# =============================================================================
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
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com sqladmin.googleapis.com || true

# 2. Setup Secrets (GTI_API_KEY & WEBRISK_API_KEY)
SECRET_NAME="harimau-gti-api-key"
WEBRISK_SECRET_NAME="harimau-webrisk-api-key"
DB_URL_SECRET="harimau-db-url"
DB_INSTANCE="harimau-db"
DB_NAME="harimau"
DB_USER="harimau"
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

# 3. Setup Cloud SQL (PostgreSQL)
echo "🐘 Checking Cloud SQL status..."
if ! gcloud sql instances describe $DB_INSTANCE --quiet > /dev/null 2>&1; then
    echo "🆕 Creating Cloud SQL instance ($DB_INSTANCE) in $REGION..."
    echo "⏳ This step typically takes 5–10 minutes (☕ grab a coffee!)..."
    
    # Prompt for Password or Generate
    echo "--------------------------------------------------------"
    read -p "🔐 Enter password for DB user '$DB_USER' (leave blank to generate): " USER_DB_PASS
    if [ -z "$USER_DB_PASS" ]; then
        # Generate 18 char alpha-numeric + symbols
        USER_DB_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c 18)
        echo "✨ Generated Password: $USER_DB_PASS"
        echo "⚠️  SAVE THIS PASSWORD SECURELY!"
    fi
    echo "--------------------------------------------------------"

    gcloud sql instances create $DB_INSTANCE \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --assign-ip \
        --quiet

    echo "🏗️  Creating database ($DB_NAME)..."
    gcloud sql databases create $DB_NAME --instance=$DB_INSTANCE --quiet

    echo "👤 Creating user ($DB_USER)..."
    gcloud sql users create $DB_USER --instance=$DB_INSTANCE --password="$USER_DB_PASS" --quiet

    # Create/Update Secret for Connection String
    # Format: postgresql://USER:PASS@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE
    DB_URL="postgresql://${DB_USER}:${USER_DB_PASS}@/${DB_NAME}?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
    
    echo "🔐 Storing DATABASE_URL in Secret Manager..."
    if ! gcloud secrets describe $DB_URL_SECRET --quiet > /dev/null 2>&1; then
        printf "$DB_URL" | gcloud secrets create $DB_URL_SECRET --data-file=-
    else
        printf "$DB_URL" | gcloud secrets versions add $DB_URL_SECRET --data-file=-
    fi
else
    echo "✅ Cloud SQL instance '$DB_INSTANCE' already exists."
    # If instance exists but secret doesn't, we might have a problem (lost password)
    # But usually we assume if instance exists, we are just redeploying.
    if ! gcloud secrets describe $DB_URL_SECRET --quiet > /dev/null 2>&1; then
        echo "⚠️  Cloud SQL instance exists but secret '$DB_URL_SECRET' is missing."
        read -p "❓ Do you want to reset the password for '$DB_USER' and recreate the secret? [y/N] " resync
        if [[ "$resync" =~ ^[yY]$ ]]; then
             echo "--------------------------------------------------------"
             read -p "🔐 Enter NEW password for DB user '$DB_USER' (leave blank to generate): " USER_DB_PASS
             if [ -z "$USER_DB_PASS" ]; then
                 USER_DB_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c 18)
                 echo "✨ Generated Password: $USER_DB_PASS"
             fi
             echo "--------------------------------------------------------"
             
             echo "🔄 Resetting password for user '$DB_USER' on instance '$DB_INSTANCE'..."
             gcloud sql users set-password $DB_USER --instance=$DB_INSTANCE --password="$USER_DB_PASS" --quiet
             
             DB_URL="postgresql://${DB_USER}:${USER_DB_PASS}@/${DB_NAME}?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
             echo "🔐 Creating secret '$DB_URL_SECRET'..."
             if ! gcloud secrets describe $DB_URL_SECRET --quiet > /dev/null 2>&1; then
                 printf "$DB_URL" | gcloud secrets create $DB_URL_SECRET --data-file=-
             else
                 printf "$DB_URL" | gcloud secrets versions add $DB_URL_SECRET --data-file=-
             fi
        else
             echo "❌ Deployment aborted. Please resolve the secret mismatch manually."
             exit 1
        fi
    fi
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
if ! gcloud secrets describe $DB_URL_SECRET --quiet > /dev/null 2>&1; then
    echo "❌ Error: Secret '$DB_URL_SECRET' does not exist."
    exit 1
fi

# 4. Grant Access to Cloud Run SA (Secret Manager + Vertex AI + Cloud SQL)
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

# Cloud SQL Access
if ! gcloud projects get-iam-policy $PROJECT_ID --format="json(bindings)" | grep -q "roles/cloudsql.client.*$SERVICE_ACCOUNT_EMAIL"; then
    echo "🔐 Granting Cloud SQL Client Access..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/cloudsql.client" --condition=None --quiet > /dev/null
else
    echo "✅ Cloud SQL Client Access already granted."
fi

# Secret Manager Access (DB_URL)
if ! gcloud secrets get-iam-policy $DB_URL_SECRET --format=json | grep -q "$SERVICE_ACCOUNT_EMAIL"; then
    echo "🔐 Granting Secret Access ($DB_URL_SECRET)..."
    gcloud secrets add-iam-policy-binding $DB_URL_SECRET \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" --quiet > /dev/null
else
    echo "✅ Secret Access ($DB_URL_SECRET) already granted."
fi



# 5. Detection Agent Integration (optional)
# Set DETECTION_AGENT_URL locally to enable forwarding completed investigations to the detection agent.
# Example: export DETECTION_AGENT_URL=https://detection-agent-<PROJECT_ID>.asia-southeast1.run.app
if [ -n "$DETECTION_AGENT_URL" ]; then
    echo "🔗 Detection Agent integration enabled: $DETECTION_AGENT_URL"
    DETECTION_AGENT_VARS=",DETECTION_AGENT_ENABLED=true,DETECTION_AGENT_URL=${DETECTION_AGENT_URL}"
else
    echo "ℹ️  DETECTION_AGENT_URL not set. Detection Agent integration disabled."
    DETECTION_AGENT_VARS=",DETECTION_AGENT_ENABLED=false"
fi

# 6. Deploy Logic
if [[ "$TARGET" == "backend" || "$TARGET" == "all" ]]; then
    echo "🚀 Deploying Backend..."
    gcloud run deploy $BACKEND_SERVICE \
        --source . \
        --region $REGION \
        --allow-unauthenticated \
        --set-env-vars "LOG_LEVEL=DEBUG,MAX_DEPTH=2,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION}${DETECTION_AGENT_VARS}" \
        --set-secrets "VT_APIKEY=${SECRET_NAME}:latest,GTI_API_KEY=${SECRET_NAME}:latest,WEBRISK_API_KEY=${WEBRISK_SECRET_NAME}:latest,DATABASE_URL=${DB_URL_SECRET}:latest" \
        --add-cloudsql-instances ${PROJECT_ID}:${REGION}:${DB_INSTANCE} \
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