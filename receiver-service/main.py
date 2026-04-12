import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google.cloud import pubsub_v1

# this creates the FastAPI APP
app = FastAPI(title="Receiver Service")

# readings environment variables
# PUBSUB_TOPIC_PATH: full path of the Pub/Sub topic
# LOCAL_MOCK_PUBLISH: if true, skip real Pub/Sub publishing for local testing
topic_path = os.getenv("PUBSUB_TOPIC_PATH")
local_mock = os.getenv("LOCAL_MOCK_PUBLISH", "true").lower() == "true"

# request body of the post request
# defines that total points must be greater than 0
class EstimatePiRequest(BaseModel):
    total_points: int = Field(..., gt=0, description="Number of random points to simulate")

# quick health check to see and confirm that the service is working
@app.get("/health")
def health_check():
    return {"message": "Receiver service is running"}

# main reciever endpoint: it accepts the points and create event payload!

# note:
# currently it is local testing soo it will be changed later: either mock-publishes it locally or sends it to Pub/Sub

@app.post("/estimate_pi", status_code=202)
def estimate_pi(request: EstimatePiRequest):
    job_id = str(uuid.uuid4())


# build the event payload that will be sent to the worker service
    event_payload = {
        "job_id": job_id,
        "total_points": request.total_points,
        "event_type": "pi_estimation_requested",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


    
    # do not call Pub/Sub, just print the payload and return success
    # local testing mode meaning that there will not call Pub/Sub!
    if local_mock:
        print("MOCK publish:", event_payload)
        return {
            "message": "Request accepted (mock publish)",
            "job_id": job_id,
            "total_points": request.total_points,
        }

    if not topic_path:
        raise HTTPException(status_code=500, detail="PUBSUB_TOPIC_PATH is not set")

    publisher = pubsub_v1.PublisherClient()

    publish_future = publisher.publish(
        topic_path,
        json.dumps(event_payload).encode("utf-8"),
        event_type="pi_estimation_requested",
    )
    publish_future.result(timeout=10)

    return {
        "message": "Request accepted",
        "job_id": job_id,
        "total_points": request.total_points,
    }