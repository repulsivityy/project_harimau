################################################################################
#
# Terraform configuration for Harimau 
#
# This configuration deploys the Harimau backend and frontend to Google Cloud Run
#
################################################################################
terraform {
  backend "gcs" {
    bucket = "dom-terraform-state-backup"
    prefix = "terraform/state/app"
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable Cloud Run API
resource "google_project_service" "run_api" {
  service = "run.googleapis.com"
  disable_on_destroy = false
}

# Backend Service
resource "google_cloud_run_service" "backend" {
  name     = "harimau-backend"
  location = var.region

  template {
    metadata {
      annotations = {
        "run.googleapis.com/cloudsql-instances" = "${var.project_id}:${var.region}:harimau-db"
        # Mirrors `--no-cpu-throttling` in deploy.sh. Required: the background
        # investigation worker keeps running after the HTTP response is sent,
        # so the CPU must stay allocated outside request handling.
        "run.googleapis.com/cpu-throttling" = "false"
      }
    }

    spec {
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/harimau/backend:latest"
        
        env {
          name = "DATABASE_URL"
          value_from {
            secret_key_ref {
              name = "harimau-db-url"
              key  = "latest"
            }
          }
        }
        # Required: backend exits 1 at startup if unset (fail-closed auth).
        env {
          name = "HARIMAU_API_KEY"
          value_from {
            secret_key_ref {
              name = "harimau-api-key"
              key  = "latest"
            }
          }
        }
        env {
          name = "DETECTION_AGENT_ENABLED"
          value = "false"
        }
        env {
          name = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name = "GOOGLE_CLOUD_REGION"
          value = var.region
        }
        env {
          name = "GTI_API_KEY"
          value_from {
            secret_key_ref {
              name = "harimau-gti-api-key"
              key  = "latest"
            }
          }
        }
        env {
          name = "LOG_LEVEL"
          value = "DEBUG"
        }
        env {
          name  = "HUNT_ITERATIONS"
          value = "3"
        }
        env {
          name = "SHODAN_API_KEY"
          value_from {
            secret_key_ref {
              name = "harimau-shodan-api-key"
              key  = "latest"
            }
          }
        }
        env {
          name = "VT_APIKEY"
          value_from {
            secret_key_ref {
              name = "harimau-gti-api-key"
              key  = "latest"
            }
          }
        }
        env {
          name = "WEBRISK_API_KEY"
          value_from {
            secret_key_ref {
              name = "harimau-webrisk-api-key"
              key  = "latest"
            }
          }
        }

        # Mirrors `--command`/`--args` in deploy.sh. Same values as the image
        # CMD in backend/Dockerfile, but set explicitly: deploy.sh writes them
        # onto the service as an override, so omitting them here makes
        # `terraform apply` clear the override and show perpetual drift.
        command = ["uvicorn"]
        args    = ["backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

        # Mirrors `--memory=2048Mi --cpu=2` in deploy.sh.
        resources {
          limits = {
            cpu    = "2"
            memory = "2048Mi"
          }
        }
      }

      # Mirrors `--timeout=600` in deploy.sh. Investigations routinely exceed
      # the 300s Cloud Run default.
      timeout_seconds = 600
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  lifecycle {
    ignore_changes = [
      template[0].spec[0].containers[0].image,
    ]
  }
}

# Frontend Service
resource "google_cloud_run_service" "frontend" {
  name     = "harimau-frontend"
  location = var.region

  template {
    spec {
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/harimau/frontend:latest"
        env {
          name = "BACKEND_URL"
          value = google_cloud_run_service.backend.status[0].url
        }
        # Required: frontend exits 1 at startup (instrumentation.ts) if unset,
        # and the API proxy route injects it as the x-harimau-api-key header.
        env {
          name = "HARIMAU_API_KEY"
          value_from {
            secret_key_ref {
              name = "harimau-api-key"
              key  = "latest"
            }
          }
        }
        ports {
            container_port = 3000
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  lifecycle {
    ignore_changes = [
      template[0].spec[0].containers[0].image,
    ]
  }
}

# Allow public access (MVP Phase)
data "google_iam_policy" "noauth" {
  binding {
    role = "roles/run.invoker"
    members = ["allUsers"]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth_backend" {
  location = google_cloud_run_service.backend.location
  project  = google_cloud_run_service.backend.project
  service  = google_cloud_run_service.backend.name
  policy_data = data.google_iam_policy.noauth.policy_data
}

resource "google_cloud_run_service_iam_policy" "noauth_frontend" {
  location = google_cloud_run_service.frontend.location
  project  = google_cloud_run_service.frontend.project
  service  = google_cloud_run_service.frontend.name
  policy_data = data.google_iam_policy.noauth.policy_data
}

