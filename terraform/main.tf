# ══════════════════════════════════════════════════════════════════
# MaaS — Math as a Service
# Terraform Infrastructure for Monte Carlo π Estimation (SWE 455 HW2)
# ══════════════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required GCP APIs ─────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "apigateway.googleapis.com",
    "servicecontrol.googleapis.com",
    "servicemanagement.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ══════════════════════════════════════════════════════════════════
# SERVICE ACCOUNTS
# ══════════════════════════════════════════════════════════════════

# Service account for the Receiver Service (publishes to Pub/Sub)
resource "google_service_account" "receiver_sa" {
  account_id   = "receiver-service-sa"
  display_name = "Receiver Service Account"
  depends_on   = [google_project_service.apis]
}

# Service account for the Worker Service (writes to Firestore)
resource "google_service_account" "worker_sa" {
  account_id   = "worker-service-sa"
  display_name = "Worker Service Account"
  depends_on   = [google_project_service.apis]
}

# Service account for Pub/Sub to invoke the Worker Cloud Run service
resource "google_service_account" "pubsub_invoker_sa" {
  account_id   = "pubsub-invoker-sa"
  display_name = "Pub/Sub Cloud Run Invoker"
  depends_on   = [google_project_service.apis]
}

# ── IAM: Receiver can publish to Pub/Sub ─────────────────────────
resource "google_project_iam_member" "receiver_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.receiver_sa.email}"
}

# ── IAM: Worker can write to Firestore ───────────────────────────
resource "google_project_iam_member" "worker_firestore_writer" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker_sa.email}"
}

# ── IAM: Pub/Sub invoker can call the Worker Cloud Run service ────
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoke_worker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker_sa.email}"
}

# ══════════════════════════════════════════════════════════════════
# CLOUD PUB/SUB (Event Bridge)
# ══════════════════════════════════════════════════════════════════

resource "google_pubsub_topic" "pi_topic" {
  name       = var.pubsub_topic_name
  depends_on = [google_project_service.apis]
}

# Push subscription — Pub/Sub delivers messages directly to the Worker
resource "google_pubsub_subscription" "pi_subscription" {
  name  = "${var.pubsub_topic_name}-sub"
  topic = google_pubsub_topic.pi_topic.name

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/pubsub/push"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker_sa.email
    }
  }

  ack_deadline_seconds       = 600   # 10 min — enough for 10M points
  message_retention_duration = "600s"

  depends_on = [google_cloud_run_v2_service.worker]
}

# ══════════════════════════════════════════════════════════════════
# CLOUD FIRESTORE (Data Store)
# ══════════════════════════════════════════════════════════════════

resource "google_firestore_database" "pi_db" {
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
  depends_on              = [google_project_service.apis]
}

# ══════════════════════════════════════════════════════════════════
# CLOUD RUN — RECEIVER SERVICE
# ══════════════════════════════════════════════════════════════════

resource "google_cloud_run_v2_service" "receiver" {
  name     = "receiver-service"
  location = var.region

  template {
    service_account = google_service_account.receiver_sa.email

    containers {
      image = var.receiver_image

      ports {
        container_port = 8080
      }

      env {
        name  = "PUBSUB_TOPIC_PATH"
        value = google_pubsub_topic.pi_topic.id
      }

      env {
        name  = "LOCAL_MOCK_PUBLISH"
        value = "false"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_service.apis,
    google_pubsub_topic.pi_topic,
  ]
}

# Allow unauthenticated access to the Receiver (API Gateway will call it)
resource "google_cloud_run_v2_service_iam_member" "receiver_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.receiver.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ══════════════════════════════════════════════════════════════════
# CLOUD RUN — WORKER SERVICE
# ══════════════════════════════════════════════════════════════════

resource "google_cloud_run_v2_service" "worker" {
  name     = "worker-service"
  location = var.region

  template {
    service_account = google_service_account.worker_sa.email

    containers {
      image = var.worker_image

      ports {
        container_port = 8080
      }

      env {
        name  = "FIRESTORE_COLLECTION"
        value = var.firestore_collection
      }

      env {
        name  = "LOCAL_MOCK_FIRESTORE"
        value = "false"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 50   # scales up to match concurrent messages
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.pi_db,
  ]
}

# ══════════════════════════════════════════════════════════════════
# API GATEWAY
# ══════════════════════════════════════════════════════════════════

# OpenAPI spec that defines the single route: POST /estimate_pi
resource "google_api_gateway_api" "maas_api" {
  provider = google
  api_id   = "maas-api"
  depends_on = [google_project_service.apis]
}

resource "google_api_gateway_api_config" "maas_api_config" {
  provider      = google
  api           = google_api_gateway_api.maas_api.api_id
  api_config_id = "maas-api-config-v1"

  openapi_documents {
    document {
      path = "openapi.yaml"
      contents = base64encode(<<-YAML
        swagger: "2.0"
        info:
          title: "MaaS API"
          description: "Math as a Service — Monte Carlo π Estimation"
          version: "1.0.0"
        host: "maas-api.apigateway.${var.project_id}.cloud.goog"
        schemes:
          - "https"
        produces:
          - "application/json"
        paths:
          /estimate_pi:
            post:
              summary: "Submit a Monte Carlo π estimation job"
              operationId: "estimatePi"
              consumes:
                - "application/json"
              parameters:
                - in: body
                  name: body
                  required: true
                  schema:
                    type: object
                    properties:
                      total_points:
                        type: integer
                        description: "Number of random points for Monte Carlo simulation"
              responses:
                "202":
                  description: "Job accepted"
              x-google-backend:
                address: "${google_cloud_run_v2_service.receiver.uri}/estimate_pi"
        YAML
      )
    }
  }

  depends_on = [google_cloud_run_v2_service.receiver]
}

resource "google_api_gateway_gateway" "maas_gateway" {
  provider   = google
  api_config = google_api_gateway_api_config.maas_api_config.id
  gateway_id = "maas-gateway"
  region     = var.region
  depends_on = [google_api_gateway_api_config.maas_api_config]
}
