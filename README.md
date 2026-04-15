# 🔢 Math as a Service (MaaS) — Monte Carlo π Estimation

> **SWE 455: Cloud Applications Engineering — Homework 2**
> Term 252 | Group of 3 | Due: April 11 @ 11:59 PM

A scalable, event-driven, serverless backend that estimates the value of **π** using Monte Carlo simulation, exposed as a REST API on Google Cloud.

---

## 📋 Table of Contents

- [Architecture](#architecture)
- [Homework Structure](#homework-structure)
- [Services](#services)
- [Infrastructure (Terraform)](#infrastructure-terraform)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Load Testing](#load-testing)
- [Cloud Run Analytics](#cloud-run-analytics)

---

## Architecture

### Overview

This system implements an **event-driven, serverless architecture** on Google Cloud Platform. When a client sends a request to estimate π, the **Receiver Service** immediately acknowledges it with a `202 Accepted` response and publishes an event to **Cloud Pub/Sub (EventBridge)**. The event then triggers the **Worker Service** (running on Cloud Run), which executes the Monte Carlo simulation and stores the result in **Cloud Firestore**.

### Architecture Diagram

![MaaS Architecture — Monte Carlo π Estimation](./architecture.png)

### Request Flow

| Step | Component | Action |
|------|-----------|--------|
| 1 | **Client** | Sends `POST /estimate_pi` with `{"total_points": N}` |
| 2 | **API Gateway** | Routes the request to the Receiver Service |
| 3 | **Receiver Service** | Returns `202 Accepted` immediately (non-blocking) |
| 4 | **Receiver Service** | Publishes `pi_estimation_requested` event to Pub/Sub |
| 5 | **Cloud Pub/Sub** | Triggers the Worker Service via push subscription |
| 6 | **Worker Service** | Runs Monte Carlo simulation with `N` random points |
| 7 | **Worker Service** | Persists `{job_id, total_points, pi_estimate, timestamp}` to Firestore |

### Component Descriptions

#### 🔵 API Gateway (Cloud API Gateway)
- Exposes the public REST endpoint: `POST /estimate_pi`
- Handles authentication, rate limiting, and routing
- Forwards valid requests to the **Receiver Service** on Cloud Run

#### 🟢 Receiver Service (Cloud Run)
- Lightweight HTTP service
- Validates the incoming JSON payload
- Responds immediately with `202 Accepted` + a `job_id`
- Publishes an event to Cloud Pub/Sub containing `job_id` and `total_points`

#### 🟠 Cloud Pub/Sub (EventBridge)
- Acts as the **event bridge** between the Receiver and Worker services
- Decouples the two services, enabling asynchronous, scalable processing
- Push subscription delivers messages directly to the Worker Service endpoint

#### 🟣 Worker Service (Cloud Run)
- Triggered by Pub/Sub push subscription
- Executes the Monte Carlo π estimation algorithm:
  ```python
  def estimate_pi(n):
      inside_circle = 0
      for _ in range(n):
          x, y = random.uniform(-1, 1), random.uniform(-1, 1)
          if x**2 + y**2 <= 1:
              inside_circle += 1
      return (4 * inside_circle) / n
  ```
- Stores results in Cloud Firestore

#### 🔴 Cloud Firestore (Data Store)
- NoSQL document database
- Stores each simulation result with:
  - `job_id` — unique identifier
  - `total_points` — number of Monte Carlo points used
  - `pi_estimate` — computed value of π
  - `timestamp` — UTC time of completion
  - `duration_ms` — execution time in milliseconds

---

## Homework Structure

```
maas-pi-estimation/
├── receiver-service/
│   ├── Dockerfile
│   ├── main.py          # FastAPI app: POST /estimate_pi
│   └── requirements.txt
├── worker-service/
│   ├── Dockerfile
│   ├── main.py          # Pub/Sub consumer + Monte Carlo simulation
│   └── requirements.txt
├── terraform/
│   ├── main.tf          # Core infrastructure
│   ├── variables.tf     # Input variables
│   └── outputs.tf       # Output values (URLs, IDs)
├── load-test/
│   └── load_test.py     # 50 concurrent requests × 10M points
├── architecture.png     # Architecture diagram
└── README.md
```

---

## Services

### Receiver Service

| Property | Value |
|----------|-------|
| Runtime  | Python 3.11 |
| Framework | FastAPI |
| Port | 8080 |
| Endpoint | `POST /estimate_pi` |
| Response | `202 Accepted` + `{ "job_id": "..." }` |

### Worker Service

| Property | Value |
|----------|-------|
| Runtime  | Python 3.11 |
| Framework | FastAPI (Pub/Sub push endpoint) |
| Port | 8080 |
| Trigger | Cloud Pub/Sub push subscription |
| Max instances | Auto-scales based on queue depth |

---

## Infrastructure (Terraform)

The following GCP resources are provisioned via Terraform:

| Resource | Type | Description |
|----------|------|-------------|
| `google_api_gateway_api` | API Gateway | Public REST API |
| `google_cloud_run_service` (receiver) | Cloud Run | Receiver microservice |
| `google_cloud_run_service` (worker) | Cloud Run | Worker microservice |
| `google_pubsub_topic` | Pub/Sub | Event bridge topic |
| `google_pubsub_subscription` | Pub/Sub | Push subscription to worker |
| `google_firestore_database` | Firestore | Result data store |

---

## Getting Started

### Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed & authenticated
- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.5
- [Docker](https://www.docker.com/) installed
- A GCP project with billing enabled

### Deployment

```bash
# 1. Clone the repository
git clone https://github.com/Rana-Elborma/maas-pi-estimation.git
cd maas-pi-estimation
```

### Local Development (without GCP)

Each service has its own virtual environment. Run these once to set them up:

```bash
# Receiver Service
cd receiver-service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Worker Service (separate terminal)
cd ../worker-service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Start the receiver locally (mock mode — no real Pub/Sub needed):

```bash
cd receiver-service
LOCAL_MOCK_PUBLISH=true .venv/bin/uvicorn main:app --reload --port 8080
```

Test it:

```bash
curl -X POST http://localhost:8080/estimate_pi \
  -H "Content-Type: application/json" \
  -d '{"total_points": 100000}'
```

### GCP Deployment

```bash
# 2. Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# 3. Deploy infrastructure
cd terraform
terraform init
terraform apply -var="project_id=YOUR_PROJECT_ID"

# 4. Get the API Gateway URL
terraform output api_gateway_url
```

---

## API Reference

### `POST /estimate_pi`

Submits a Monte Carlo π estimation job.

**Request:**
```http
POST /estimate_pi
Content-Type: application/json

{
  "total_points": 10000000
}
```

**Response:**
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "job_id": "abc123",
  "status": "accepted",
  "message": "Job queued. Results will be stored in Firestore."
}
```

---

## Load Testing

The system was tested with **50 concurrent requests**, each requesting **10,000,000 Monte Carlo points**.

```bash
cd load-test
pip install httpx
python load_test.py --url <API_GATEWAY_URL> --concurrency 50 --points 10000000
```

### Load Test Summary

> ⚠️ **Run the load test after deploying to GCP, then fill in the table below.**
>
> ```bash
> cd load-test
> python load_test.py --url <API_GATEWAY_URL> --concurrency 50 --points 10000000
> ```

| Metric | Value |
|--------|-------|
| Total requests | 50 |
| Points per request | 10,000,000 |
| Concurrency | 50 |
| Total time | *(fill in)* |
| Avg response time (202) | *(fill in)* |
| Min / Max / P95 latency | *(fill in)* |
| Success rate | *(fill in)* |

---

## Cloud Run Analytics

> 📊 **Populate this section after deploying to GCP and running the load test.**
> Navigate to: [Google Cloud Console → Cloud Run](https://console.cloud.google.com/run) → select service → **Metrics** tab.

### How to capture screenshots
1. Go to your GCP project's Cloud Run console
2. Select **receiver-service** or **worker-service**
3. Click the **Metrics** tab
4. Set time range to cover the load test window
5. Screenshot each graph and embed it below

### Receiver Service Metrics

<!-- Replace *(screenshot)* cells with: ![description](./screenshots/receiver-request-count.png) -->

| Metric | Graph |
|--------|-------|
| Request count | *(screenshot)* |
| Request latency (p50/p95/p99) | *(screenshot)* |
| Container instance count | *(screenshot)* |
| CPU utilization | *(screenshot)* |

### Worker Service Metrics

| Metric | Graph |
|--------|-------|
| Request count (Pub/Sub triggers) | *(screenshot)* |
| Request latency per job | *(screenshot)* |
| Container instance count (auto-scale) | *(screenshot)* |
| Memory utilization | *(screenshot)* |

### Pub/Sub Metrics

| Metric | Graph |
|--------|-------|
| Message publish rate | *(screenshot)* |
| Subscription message backlog | *(screenshot)* |
| Oldest unacked message age | *(screenshot)* |

### Firestore

| Metric | Graph |
|--------|-------|
| Read/Write operations | *(screenshot)* |
| Stored documents (50 results) | *(screenshot)* |

### Sample Simulation Results

> Replace the example below with real results from Firestore after running the load test.

```json
[
  {
    "job_id": "abc-123-...",
    "total_points": 10000000,
    "pi_estimate": 3.14159...,
    "timestamp": "2026-04-11T10:00:00Z",
    "duration_ms": 0
  }
]
```

---

## Contributors

| Name | Role |
|------|------|
| Rana Elborma | Architecture, Receiver Service, Terraform |
| *(Team member 2)* | Worker Service |
| *(Team member 3)* | Load Testing / Firestore |

---

## License

This homework is submitted for academic purposes — SWE 455, Term 252.
