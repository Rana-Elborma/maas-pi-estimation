"""
MaaS Load Test
==============
Sends 50 concurrent POST /estimate_pi requests to the API Gateway,
then connects via WebSocket to receive the π result in real time.

Flow per request:
  1. POST /estimate_pi  → 202 Accepted + job_id
  2. Connect WebSocket  → wss://<websocket-url>/ws/<job_id>
  3. Wait for result    → {job_id, pi_estimate, duration_ms, ...}
  4. Record end-to-end latency

Usage:
    pip install httpx websockets
    python load_test.py \
        --url <API_GATEWAY_URL> \
        --ws-url <WEBSOCKET_SERVICE_URL> \
        --concurrency 50 \
        --points 10000000
"""

import argparse
import asyncio
import json
import time
from statistics import mean, median, quantiles

import httpx
import websockets


async def send_request(
    client: httpx.AsyncClient,
    api_url: str,
    ws_url: str,
    points: int,
    request_number: int,
    ws_timeout: float,
) -> dict:
    """
    Full end-to-end request:
      POST /estimate_pi → WebSocket /ws/{job_id} → receive result
    """
    payload = {"total_points": points}
    overall_start = time.perf_counter()

    # ── Step 1: POST /estimate_pi ──────────────────────────────────────────────
    try:
        response = await client.post(api_url, json=payload, timeout=30.0)
        post_elapsed = round((time.perf_counter() - overall_start) * 1000, 2)

        if response.status_code != 202:
            print(f"  [DEBUG] Request {request_number}: status={response.status_code} body={response.text[:200]}")
            return {
                "request":       request_number,
                "status_code":   response.status_code,
                "post_ms":       post_elapsed,
                "e2e_ms":        None,
                "pi_estimate":   None,
                "job_id":        None,
                "success":       False,
                "error":         f"HTTP {response.status_code}: {response.text[:100]}",
            }

        job_id = response.json().get("job_id")
        print(f"  [DEBUG] Request {request_number}: 202 OK, job_id={job_id}")
    except Exception as exc:
        return {
            "request":     request_number,
            "status_code": None,
            "post_ms":     round((time.perf_counter() - overall_start) * 1000, 2),
            "e2e_ms":      None,
            "pi_estimate": None,
            "job_id":      None,
            "success":     False,
            "error":       str(exc),
        }

    # ── Step 2 & 3: WebSocket → wait for result ────────────────────────────────
    ws_endpoint = f"{ws_url.rstrip('/')}/ws/{job_id}"
    # Cloud Run uses https:// — convert to wss:// for WebSocket
    ws_endpoint = ws_endpoint.replace("https://", "wss://").replace("http://", "ws://")

    pi_estimate = None
    ws_error    = None

    try:
        ssl_ctx = __import__("ssl").create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = __import__("ssl").CERT_NONE
        async with websockets.connect(ws_endpoint, ssl=ssl_ctx, ping_timeout=ws_timeout) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
            result      = json.loads(raw)
            pi_estimate = result.get("pi_estimate")
    except asyncio.TimeoutError:
        ws_error = f"WebSocket timeout after {ws_timeout}s"
    except Exception as exc:
        ws_error = str(exc)

    e2e_elapsed = round((time.perf_counter() - overall_start) * 1000, 2)

    return {
        "request":     request_number,
        "status_code": 202,
        "post_ms":     post_elapsed,
        "e2e_ms":      e2e_elapsed,
        "pi_estimate": pi_estimate,
        "job_id":      job_id,
        "success":     pi_estimate is not None,
        "error":       ws_error,
    }


async def run_load_test(api_url: str, ws_url: str, concurrency: int, points: int, ws_timeout: float):
    endpoint = f"{api_url.rstrip('/')}/estimate_pi"

    print(f"\nStarting load test")
    print(f"  API endpoint  : {endpoint}")
    print(f"  WebSocket svc : {ws_url}")
    print(f"  Requests      : {concurrency}")
    print(f"  Points        : {points:,}")
    print(f"  WS timeout    : {ws_timeout}s\n")

    overall_start = time.perf_counter()

    async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
        tasks = [
            send_request(client, endpoint, ws_url, points, i + 1, ws_timeout)
            for i in range(concurrency)
        ]
        results = await asyncio.gather(*tasks)

    overall_elapsed = round((time.perf_counter() - overall_start) * 1000, 2)

    # ── Print per-request results ──────────────────────────────────────────────
    print(f"{'#':>4}  {'POST(ms)':>10}  {'E2E(ms)':>10}  {'π estimate':>12}  Job ID")
    print("-" * 80)
    for r in results:
        e2e     = f"{r['e2e_ms']:>10.0f}" if r["e2e_ms"] else "    timeout"
        pi      = f"{r['pi_estimate']:.6f}" if r["pi_estimate"] else "      N/A "
        job     = r["job_id"] or r.get("error", "")
        print(f"{r['request']:>4}  {r['post_ms']:>10.2f}  {e2e}  {pi:>12}  {job}")

    # ── Summary ────────────────────────────────────────────────────────────────
    post_latencies = [r["post_ms"] for r in results]
    e2e_latencies  = [r["e2e_ms"] for r in results if r["e2e_ms"] is not None]
    successes      = [r for r in results if r["success"]]
    failures       = [r for r in results if not r["success"]]

    print("\n" + "=" * 80)
    print("Load Test Summary")
    print("=" * 80)
    print(f"  Total requests      : {concurrency}")
    print(f"  Points per request  : {points:,}")
    print(f"  Total wall time     : {overall_elapsed:,.0f} ms")
    print(f"  Successful (WS rcvd): {len(successes)}")
    print(f"  Failed              : {len(failures)}")
    print(f"  Success rate        : {len(successes)/concurrency*100:.1f}%")

    print(f"\n  POST /estimate_pi latency (202 response):")
    print(f"    Min    : {min(post_latencies):.2f} ms")
    print(f"    Avg    : {mean(post_latencies):.2f} ms")
    print(f"    Median : {median(post_latencies):.2f} ms")
    if len(post_latencies) >= 20:
        p = quantiles(post_latencies, n=100)
        print(f"    p95    : {p[94]:.2f} ms")
    print(f"    Max    : {max(post_latencies):.2f} ms")

    if e2e_latencies:
        print(f"\n  End-to-end latency (POST → WebSocket result):")
        print(f"    Min    : {min(e2e_latencies)/1000:.1f} s")
        print(f"    Avg    : {mean(e2e_latencies)/1000:.1f} s")
        print(f"    Median : {median(e2e_latencies)/1000:.1f} s")
        if len(e2e_latencies) >= 20:
            p = quantiles(e2e_latencies, n=100)
            print(f"    p95    : {p[94]/1000:.1f} s")
        print(f"    Max    : {max(e2e_latencies)/1000:.1f} s")

    print("=" * 80)

    if failures:
        print("\nFailed requests:")
        for r in failures:
            print(f"  #{r['request']:>2}  job={r['job_id']}  error={r['error']}")


def main():
    parser = argparse.ArgumentParser(description="MaaS Load Test — with WebSocket")
    parser.add_argument("--url",         required=True, help="API Gateway base URL")
    parser.add_argument("--ws-url",      required=True, help="WebSocket Service Cloud Run URL")
    parser.add_argument("--concurrency", type=int,   default=50,         help="Concurrent requests (default: 50)")
    parser.add_argument("--points",      type=int,   default=10_000_000, help="Monte Carlo points per request (default: 10000000)")
    parser.add_argument("--ws-timeout",  type=float, default=600.0,      help="Seconds to wait for WebSocket result (default: 600)")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.ws_url, args.concurrency, args.points, args.ws_timeout))


if __name__ == "__main__":
    main()
