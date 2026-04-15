output "api_gateway_url" {
  description = "Public URL of the API Gateway — use this to call POST /estimate_pi"
  value       = "https://${google_api_gateway_gateway.maas_gateway.default_hostname}"
}

output "receiver_service_url" {
  description = "Cloud Run URL of the Receiver Service (internal)"
  value       = google_cloud_run_v2_service.receiver.uri
}

output "worker_service_url" {
  description = "Cloud Run URL of the Worker Service (internal)"
  value       = google_cloud_run_v2_service.worker.uri
}

output "pubsub_topic" {
  description = "Full name of the Pub/Sub topic"
  value       = google_pubsub_topic.pi_topic.id
}

output "pubsub_subscription" {
  description = "Full name of the Pub/Sub push subscription"
  value       = google_pubsub_subscription.pi_subscription.id
}

output "firestore_database" {
  description = "Firestore database name"
  value       = google_firestore_database.pi_db.name
}
