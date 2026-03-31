variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud Region"
  type        = string
  default     = "asia-southeast1"
}

variable "db_password" {
  description = "Database password for user harimau"
  type        = string
  sensitive   = true
}
