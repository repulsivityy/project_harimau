provider "google" {
  project = var.project_id
  region  = var.region
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
  deletion_protection = false # Set to false since we want to be able to destroy/rebuild easily in non-prod
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
