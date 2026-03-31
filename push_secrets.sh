#!/bin/bash
# =============================================================================
# Project Harimau — Push Secrets to Secret Manager
# =============================================================================
# This script reads secrets from environment variables or a .env file and
# pushes them to Google Cloud Secret Manager. This avoids storing secrets
# in Terraform state files.
# =============================================================================

set -e

# Load .env file if it exists
if [ -f .env ]; then
    echo "Loading .env file..."
    export $(grep -v '^#' .env | xargs)
fi

PROJECT_ID=$(gcloud config get-value project)
echo "Using Project: $PROJECT_ID"

function push_secret() {
    local secret_name=$1
    local secret_value=$2

    if [ -z "$secret_value" ]; then
        echo "⚠️  Skipping $secret_name (Value is empty)"
        return
    fi

    echo "Pushing secret: $secret_name..."
    
    # Check if secret exists
    if ! gcloud secrets describe "$secret_name" --quiet > /dev/null 2>&1; then
        echo "Creating secret container $secret_name..."
        printf "$secret_value" | gcloud secrets create "$secret_name" --data-file=- --quiet
    else
        echo "Adding new version to $secret_name..."
        printf "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --quiet
    fi
    echo "✅ Done with $secret_name"
}

# Push required secrets
push_secret "harimau-gti-api-key" "$GTI_API_KEY"
push_secret "harimau-webrisk-api-key" "$WEBRISK_API_KEY"
push_secret "harimau-shodan-api-key" "$SHODAN_API_KEY"

# Optional: DB URL if you have it locally.
# If managed by Terraform, you might not need to push it here.
# push_secret "harimau-db-url" "$DATABASE_URL"

echo "🎉 Secrets push complete!"
