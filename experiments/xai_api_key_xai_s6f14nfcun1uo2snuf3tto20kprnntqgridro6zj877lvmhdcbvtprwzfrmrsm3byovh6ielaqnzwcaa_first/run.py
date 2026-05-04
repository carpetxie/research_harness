"""
Minimal first experiment: hit the xAI /v1/models endpoint and print shape/size.

Run:  uv run python -m experiments.xai_api_key_xai_s6f14nfcun1uo2snuf3tto20kprnntqgridro6zj877lvmhdcbvtprwzfrmrsm3byovh6ielaqnzwcaa_first.run
"""

from __future__ import annotations

import argparse
import json

from src.data.xai_api_key_xai_s6f14nfcun1uo2snuf3tto20kprnntqgridro6zj877lvmhdcbvtprwzfrmrsm3byovh6ielaqnzwcaa import (
    XAIClient,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse cached models response if present.",
    )
    args = parser.parse_args()

    client = XAIClient(data_dir="data/xai_first")
    series = "models"

    if args.skip_fetch and client.is_cached(endpoint=series):
        data = client.load(endpoint=series)
        source = "cache"
    else:
        data = client.fetch(endpoint=series)
        client._save_file(data, client.cache_path(endpoint=series))
        source = "network"

    # Report shape / size of the small dataset.
    models = data.get("data", []) if isinstance(data, dict) else []
    payload_bytes = len(json.dumps(data).encode("utf-8"))

    print(f"[xai_first] source       : {source}")
    print(f"[xai_first] top-level keys: {sorted(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    print(f"[xai_first] num models    : {len(models)}")
    print(f"[xai_first] payload bytes : {payload_bytes}")
    if models:
        first_ids = [m.get("id") for m in models[:5]]
        print(f"[xai_first] first ids     : {first_ids}")


if __name__ == "__main__":
    main()
