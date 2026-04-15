import asyncio
import base64
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException

app = FastAPI(title="WebSocket Service")

# In-memory map: job_id -> active WebSocket connection
# Note: works for demo purposes; production would use Redis for multi-instance sharing
active_connections: dict[str, WebSocket] = {}


@app.get("/health")
def health_check():
    return {"message": "WebSocket service is running"}


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    Client connects here after submitting a job.
    Holds the connection open until the worker publishes the result.
    """
    await websocket.accept()
    active_connections[job_id] = websocket
    print(f"[WS] Client connected, waiting for job {job_id}")

    try:
        # Keep alive — result will be pushed by /pubsub/push endpoint
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected for job {job_id}")
    finally:
        active_connections.pop(job_id, None)


@app.post("/pubsub/push")
async def pubsub_push(request: Request):
    """
    Receives a Pub/Sub push message containing the simulation result,
    then forwards it to the waiting WebSocket client.
    """
    body = await request.json()

    try:
        pubsub_message = body["message"]
        data_bytes = base64.b64decode(pubsub_message["data"])
        result = json.loads(data_bytes)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Pub/Sub message: {exc}")

    job_id = result.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id in result payload")

    print(f"[WS] Result received for job {job_id}: π ≈ {result.get('pi_estimate')}")

    ws = active_connections.get(job_id)
    if ws:
        try:
            await ws.send_json(result)
            print(f"[WS] Result pushed to client for job {job_id}")
        except Exception as exc:
            print(f"[WS] Failed to push result for job {job_id}: {exc}")
        finally:
            active_connections.pop(job_id, None)
    else:
        print(f"[WS] No active connection for job {job_id} — result stored in Firestore only")

    return {"status": "ok"}
