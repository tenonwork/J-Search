"""
run.py — Unified J-Search pipeline entry point.

Runs both ingestion sources (remote jobs + local merchant leads) and
compiles them into a single dashboard.html, which opens automatically.

Usage:
    python run.py
"""

from fetch_live_jobs import get_live_remote_jobs
from fetch_local_merchants import get_local_merchants_ddg
from job_dashboard import build_dashboard


def run_pipeline():
    print("=" * 50)
    print("  J-Search Pipeline Starting")
    print("=" * 50)

    # Run both fetchers
    remote_jobs  = get_live_remote_jobs()
    local_leads  = get_local_merchants_ddg()

    print()
    print(f"  Remote jobs fetched : {len(remote_jobs)}")
    print(f"  Local leads fetched : {len(local_leads)}")
    print()

    # Build the combined dashboard
    build_dashboard(remote_jobs=remote_jobs, local_leads=local_leads)


if __name__ == "__main__":
    run_pipeline()
