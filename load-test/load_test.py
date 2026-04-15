"""
MaaS Load Test
==============
Sends 50 concurrent POST /estimate_pi requests to the API Gateway,
each with 10,000,000 Monte Carlo points.

Usage:
    pip install httpx
    python load_test.py --url <API_GATEWAY_URL> --concurrency 50 --points 10000000
"""

import argparse
import asyncio
import time
from statistics import mean, median, quantiles

import httpx


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    points: int,
    request_number: int,
) -> dict:
    """Send a single POST /estimate_pi request and record timing."""
    payload = {"total_points": points}
    start = time.perf_counter()
    try:
        response = await client.post(url, json=payload, timeout=30.0)
        elapsed = round((time.perf_counter() - start) * 1000, 2)  # ms
        return {
            "request": request_number,
            "status_code": response.status_code,
            "elapsed_ms": elapsed,
            "success": response.status_code == 202,
            "body": response.json() if response.status_code == 202 else response.text,
        }
    except Exception as exc:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return {
            "request": request_number,
            "status_code": None,
            "elapsed_ms": elapsed,
            "success": False,
            "body": str(exc),
        }


async def run_load_test(api_url: str, concurrency: int, points: int):
    """Send `concurrency` requests simultaneously and print a summary."""
    endpoint = f"{api_url.rstrip('/')}/estimate_pi"
    print(f"\n🚀 Starting load test")
    print(f"   Endpoint  : {endpoint}")
    print(f"   Requests  : {concurrency}")
    print(f"   Points    : {points:,}")
    print(f"   Mode      : {concurrency} concurrent\n")

    overall_start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        tasks = [
            send_request(client, endpoint, points, i + 1)
            for i in range(concurrency)
        ]
        results = await asyncio.gather(*tasks)

    overall_elapsed = round((time.perf_counter() - overall_start) * 1000, 2)

    # ── Print individual results ────────────────────────────────────────────
    print(f"{'#':>4}  {'Status':>8}  {'Latency (ms)':>14}  Job ID / Error")
    print("-" * 70)
    for r in results:
        job_id = r["body"].get("job_id", "") if isinstance(r["body"], dict) else r["body"]
        status = r["status_code"] or "ERR"
        print(f"{r['request']:>4}  {str(status):>8}  {r['elapsed_ms']:>14.2f}  {job_id}")

    # ── Summary stats ───────────────────────────────────────────────────────
    latencies = [r["elapsed_ms"] for r in results]
    successes = [r for r in results if r["success"]]
    failures  = [r for r in results if not r["success"]]

    p_values = quantiles(latencies, n=100)   # percentiles list (index 0 = p1)

    print("\n" + "=" * 70)
    print("📊 Load Test Summary")
    print("=" * 70)
    print(f"  Total requests     : {concurrency}")
    print(f"  Points per request : {points:,}")
    print(f"  Total wall time    : {overall_elapsed:,.2f} ms")
    print(f"  Successful (202)   : {len(successes)}")
    print(f"  Failed             : {len(failures)}")
    print(f"  Success rate       : {len(successes)/concurrency*100:.1f}%")
    print()
    print(f"  Latency stats (ms):")
    print(f"    Min              : {min(latencies):.2f}")
    print(f"    Avg              : {mean(latencies):.2f}")
    print(f"    Median (p50)     : {median(latencies):.2f}")
    print(f"    p95              : {p_values[94]:.2f}")
    print(f"    Max              : {max(latencies):.2f}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="MaaS Load Test")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the API Gateway (e.g. https://my-gateway-xyz.apigateway.project.cloud.goog)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Number of concurrent requests to send (default: 50)",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=10_000_000,
        help="Number of Monte Carlo points per request (default: 10000000)",
    )
    args = parser.parse_args()
    asyncio.run(run_load_test(args.url, args.concurrency, args.points))


if __name__ == "__main__":
    main()
