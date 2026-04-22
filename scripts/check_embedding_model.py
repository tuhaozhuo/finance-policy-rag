#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Check embedding model availability and vector dimension")
    parser.add_argument("--base-url", required=True, help="Embedding API base url, e.g. https://api.siliconflow.cn/v1")
    parser.add_argument("--api-key", default="", help="Embedding API key")
    parser.add_argument("--model", required=True, help="Embedding model id")
    parser.add_argument("--text", default="金融监管条文测试", help="probe text")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    payload = {"model": args.model, "input": [args.text]}
    with httpx.Client(timeout=args.timeout) as client:
        resp = client.post(f"{args.base_url.rstrip('/')}/embeddings", headers=headers, json=payload)
        resp.raise_for_status()

    data = resp.json().get("data", [])
    if not data or "embedding" not in data[0]:
        raise SystemExit("no embedding returned, check model/base-url/api-key")

    vector = data[0]["embedding"]
    output = {
        "model": args.model,
        "base_url": args.base_url,
        "dimension": len(vector),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
