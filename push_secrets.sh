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
    # printf '%s' -- never pass the value as the format string, or '%' and
    # backslash sequences inside it get interpreted and the secret is silently
    # written mangled.
    if ! gcloud secrets describe "$secret_name" --quiet > /dev/null 2>&1; then
        echo "Creating secret container $secret_name..."
        printf '%s' "$secret_value" | gcloud secrets create "$secret_name" --data-file=- --quiet
    else
        echo "Adding new version to $secret_name..."
        printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --quiet
    fi
    echo "✅ Done with $secret_name"
}

# Push required secrets
push_secret "harimau-gti-api-key" "$GTI_API_KEY"
push_secret "harimau-webrisk-api-key" "$WEBRISK_API_KEY"
push_secret "harimau-shodan-api-key" "$SHODAN_API_KEY"
push_secret "harimau-api-key" "$HARIMAU_API_KEY"

# DATABASE_URL is deliberately NOT pushed here.
#
# deploy.sh owns the harimau-db-url secret: it provisions the Cloud SQL
# instance and writes the Unix-socket DSN that Cloud Run needs --
#   postgresql://harimau:PASS@/harimau?host=/cloudsql/PROJECT:REGION:harimau-db
# -- via the /cloudsql mount granted by --add-cloudsql-instances.
#
# The DATABASE_URL in .env is the local TCP form (localhost:5432), so pushing
# it here would overwrite the Cloud SQL DSN and break the deployed backend.
# Terraform only declares the empty secret *container*, never the value.
# push_secret "harimau-db-url" "$DATABASE_URL"

echo "🎉 Secrets push complete!"
