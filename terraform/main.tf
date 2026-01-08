provider "google" {
  project = var.project_id
  region  = var.region
}

# vars.tf content embedded for simplicity
variable "project_id" {}
variable "region" { default = "asia-southeast1" }

# Enable Cloud Run API
resource "google_project_service" "run_api" {
  service = "run.googleapis.com"
  disable_on_destroy = false
}

# Backend Service (Placeholder - Actual image management is easier via gcloud for now)
resource "google_cloud_run_service" "backend" {
  name     = "harimau-backend"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/harimau-backend:latest" # Ensure image exists first
        env {
          name = "LOG_LEVEL"
          value = "INFO"
        }
      }
    }
  }
  traffic {
    percent         = 100
    latest_revision = true
  }
}

# Frontend Service
resource "google_cloud_run_service" "frontend" {
  name     = "harimau-frontend"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/harimau-frontend:latest"
        env {
          name = "BACKEND_URL"
          value = google_cloud_run_service.backend.status[0].url
        }
        ports {
            container_port = 8501
        }
      }
    }
  }
    traffic {
    percent         = 100
    latest_revision = true
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
