import base64
import json
import os
import random
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

app = FastAPI(title="Worker Service")

# ── environment ────────────────────────────────────────────────────────────────
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "pi_estimations")
LOCAL_MOCK_FIRESTORE = os.getenv("LOCAL_MOCK_FIRESTORE", "true").lower() == "true"

# ── Firestore client (lazy) ─────────────────────────────────────────────────
_db = None

def get_db():
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


# ── Monte Carlo simulation ──────────────────────────────────────────────────
def estimate_pi(n: int) -> float:
    """Estimate π using Monte Carlo simulation with n random points."""
    inside_circle = 0
    for _ in range(n):
        x, y = random.uniform(-1, 1), random.uniform(-1, 1)
        if x**2 + y**2 <= 1:
            inside_circle += 1
    return (4 * inside_circle) / n


# ── Health check ────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"message": "Worker service is running"}


# ── Pub/Sub push endpoint ────────────────────────────────────────────────────
@app.post("/pubsub/push")
async def pubsub_push(request: Request):
    """
    Receives a Pub/Sub push message, decodes it, runs the simulation,
    and saves the result to Firestore.
    """
    body = await request.json()

    # Pub/Sub wraps the payload in an envelope: { "message": { "data": "<base64>" } }
    try:
        pubsub_message = body["message"]
        data_bytes = base64.b64decode(pubsub_message["data"])
        event = json.loads(data_bytes)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Pub/Sub message: {exc}")

    job_id = event.get("job_id")
    total_points = event.get("total_points")

    if not job_id or not total_points:
        raise HTTPException(status_code=400, detail="Missing job_id or total_points in event payload")

    print(f"[Worker] Received job {job_id} with {total_points} points")

    # ── Run the simulation ─────────────────────────────────────────────────
    start_time = time.time()
    pi_estimate = estimate_pi(total_points)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    print(f"[Worker] Job {job_id} → π ≈ {pi_estimate:.6f} ({duration_ms} ms)")

    # ── Persist to Firestore ───────────────────────────────────────────────
    result = {
        "job_id": job_id,
        "total_points": total_points,
        "pi_estimate": pi_estimate,
        "duration_ms": duration_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if LOCAL_MOCK_FIRESTORE:
        # Local mode: just print the result instead of writing to Firestore
        print("MOCK Firestore write:", result)
    else:
        db = get_db()
        db.collection(FIRESTORE_COLLECTION).document(job_id).set(result)
        print(f"[Worker] Saved job {job_id} to Firestore")

    # Returning 204 tells Pub/Sub the message was processed successfully
    return {"status": "ok", "job_id": job_id, "pi_estimate": pi_estimate}
