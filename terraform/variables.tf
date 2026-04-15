variable "project_id" {
  description = "The GCP project ID to deploy resources into"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and other regional resources"
  type        = string
  default     = "us-central1"
}

variable "receiver_image" {
  description = "Docker image URI for the Receiver Service (e.g. gcr.io/PROJECT/receiver-service:latest)"
  type        = string
}

variable "worker_image" {
  description = "Docker image URI for the Worker Service (e.g. gcr.io/PROJECT/worker-service:latest)"
  type        = string
}

variable "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic used as the event bridge"
  type        = string
  default     = "pi-estimation-topic"
}

variable "firestore_collection" {
  description = "Firestore collection name for storing simulation results"
  type        = string
  default     = "pi_estimations"
}
