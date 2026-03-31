provider "google" {
  project = var.project_id
  region  = var.region
}

# vars.tf content embedded for simplicity
variable "project_id" {}
variable "region" { default = "asia-southeast1" }
variable "db_password" {
  description = "Database password for user harimau"
  type        = string
  sensitive   = true
}

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
        image = "asia-southeast1-docker.pkg.dev/virustotal-lab/cloud-run-source-deploy/harimau-backend@sha256:ed443554de2bc9a0958fab66404939858ca6d30aab39fde8b3b674a704648a09"
        env {
          name = "DATABASE_URL"
          value_from {
            secret_key_ref {
              name = "harimau-db-url"
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
          name = "MAX_DEPTH"
          value = "2"
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
        image = "gcr.io/virustotal-lab/harimau-frontend"
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

# Artifact Registry Repository
resource "google_artifact_registry_repository" "harimau_repo" {
  location      = var.region
  repository_id = "harimau"
  description   = "Docker repository for Project Harimau"
  format        = "DOCKER"
}

# Secret Manager Containers (Values managed separately)
resource "google_secret_manager_secret" "gti_api_key" {
  secret_id = "harimau-gti-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "webrisk_api_key" {
  secret_id = "harimau-webrisk-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "shodan_api_key" {
  secret_id = "harimau-shodan-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "harimau-db-url"
  replication {
    auto {}
  }
}

# Cloud SQL Instance
resource "google_sql_database_instance" "default" {
  name             = "harimau-db"
  region           = var.region
  database_version = "POSTGRES_15"
  settings {
    tier = "db-f1-micro"
  }
  deletion_protection = true 
}

# Cloud SQL Database
resource "google_sql_database" "default" {
  name     = "harimau"
  instance = google_sql_database_instance.default.name
}

# Cloud SQL User
resource "google_sql_user" "default" {
  name     = "harimau"
  instance = google_sql_database_instance.default.name
  password = var.db_password
}
