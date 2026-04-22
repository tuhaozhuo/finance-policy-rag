#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path
from time import perf_counter

import httpx


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int((len(sorted_values) - 1) * ratio)
    return sorted_values[index]


def hit_keywords(text: str, expected_keywords: list[str]) -> tuple[int, int]:
    if not expected_keywords:
        return 0, 0
    hits = sum(1 for item in expected_keywords if item and item.lower() in text.lower())
    return hits, len(expected_keywords)


def call_api(client: httpx.Client, method: str, url: str, payload: dict, timeout: float) -> tuple[bool, float, dict]:
    start = perf_counter()
    try:
        if method == "GET":
            response = client.get(url, params=payload, timeout=timeout)
        else:
            response = client.post(url, json=payload, timeout=timeout)
        latency_ms = (perf_counter() - start) * 1000
        data = response.json() if response.content else {}
        return response.status_code == 200, latency_ms, data
    except Exception as exc:
        latency_ms = (perf_counter() - start) * 1000
        return False, latency_ms, {"error": str(exc)}


def score_rows(rows: list[dict]) -> dict[str, object]:
    total = len(rows)
    success = sum(1 for item in rows if item["success"])
    accurate = sum(1 for item in rows if item["keyword_hit_ratio"] >= 0.5)
    recall_hits = sum(item["keyword_hits"] for item in rows)
    recall_total = sum(item["keyword_total"] for item in rows)
    latencies = [float(item["latency_ms"]) for item in rows]
    return {
        "total": total,
        "success": success,
        "success_rate": round(success / max(1, total), 4),
        "accuracy": round(accurate / max(1, total), 4),
        "recall": round(recall_hits / max(1, recall_total), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 0.95), 2),
    }


def evaluate_search(client: httpx.Client, base_url: str, cases: list[dict], timeout: float) -> list[dict]:
    rows = []
    for case in cases:
        ok, latency_ms, payload = call_api(
            client,
            "POST",
            f"{base_url}/search",
            {"query": case["query"], "status": case.get("status", "all"), "top_k": case.get("top_k", 5)},
            timeout,
        )
        data = payload.get("data") or {}
        citations = data.get("citations") or []
        text = "\n".join((item.get("title", "") + "\n" + item.get("chunk_text", "")) for item in citations)
        hits, total = hit_keywords(text, case.get("expected_keywords", []))
        rows.append(
            {
                "type": "search",
                "query": case["query"],
                "success": ok,
                "latency_ms": round(latency_ms, 2),
                "keyword_hits": hits,
                "keyword_total": total,
                "keyword_hit_ratio": round(hits / max(1, total), 4),
                "citations": len(citations),
            }
        )
    return rows


def evaluate_qa(client: httpx.Client, base_url: str, cases: list[dict], case_type: str, timeout: float) -> list[dict]:
    rows = []
    for case in cases:
        ok, latency_ms, payload = call_api(
            client,
            "POST",
            f"{base_url}/qa",
            {"question": case["question"], "include_expired": case.get("include_expired", True), "top_k": case.get("top_k", 5)},
            timeout,
        )
        data = payload.get("data") or {}
        citations = data.get("citations") or []
        citation_text = "\n".join((item.get("title", "") + "\n" + item.get("chunk_text", "")) for item in citations)
        text = f"{data.get('answer', '')}\n{citation_text}\n{data.get('effective_status_summary', '')}"
        hits, total = hit_keywords(text, case.get("expected_keywords", []))
        rows.append(
            {
                "type": case_type,
                "query": case["question"],
                "success": ok,
                "latency_ms": round(latency_ms, 2),
                "keyword_hits": hits,
                "keyword_total": total,
                "keyword_hit_ratio": round(hits / max(1, total), 4),
                "citations": len(citations),
                "confidence_score": data.get("confidence_score", 0),
                "generation_status": data.get("generation_status", ""),
            }
        )
    return rows


def evaluate_related(client: httpx.Client, base_url: str, cases: list[dict], timeout: float) -> list[dict]:
    rows = []
    for case in cases:
        ok, latency_ms, payload = call_api(
            client,
            "POST",
            f"{base_url}/search/related",
            {"query": case["query"], "status": case.get("status", "all"), "top_k": case.get("top_k", 5)},
            timeout,
        )
        data = payload.get("data") or {}
        citations = (data.get("anchor_citations") or []) + (data.get("related_citations") or [])
        text = "\n".join((item.get("title", "") + "\n" + item.get("chunk_text", "")) for item in citations)
        hits, total = hit_keywords(text, case.get("expected_keywords", []))
        rows.append(
            {
                "type": "related",
                "query": case["query"],
                "success": ok,
                "latency_ms": round(latency_ms, 2),
                "keyword_hits": hits,
                "keyword_total": total,
                "keyword_hit_ratio": round(hits / max(1, total), 4),
                "citations": len(citations),
            }
        )
    return rows


def render_markdown(output: dict) -> str:
    lines = [
        "# 验收评测报告",
        "",
        f"- 运行时间: {output['run_at']}",
        f"- 基准地址: {output['base_url']}",
        "",
    ]
    for name, summary in output["summary"].items():
        lines.extend(
            [
                f"## {name}",
                f"- total: {summary['total']}",
                f"- success_rate: {summary['success_rate']}",
                f"- accuracy: {summary['accuracy']}",
                f"- recall: {summary['recall']}",
                f"- avg_latency_ms: {summary['avg_latency_ms']}",
                f"- p95_latency_ms: {summary['p95_latency_ms']}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed acceptance evaluation for finance RAG APIs")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--query-file", default="data/eval/acceptance_queries.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output-json", default="docs/reports/acceptance_eval.json")
    parser.add_argument("--output-md", default="docs/reports/acceptance_eval.md")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    query_file = (root / args.query_file).resolve()
    cases = json.loads(query_file.read_text(encoding="utf-8"))

    rows_by_type: dict[str, list[dict]] = {}
    with httpx.Client() as client:
        rows_by_type["search"] = evaluate_search(client, args.base_url, cases.get("search", []), args.timeout)
        rows_by_type["qa"] = evaluate_qa(client, args.base_url, cases.get("qa", []), "qa", args.timeout)
        rows_by_type["related"] = evaluate_related(client, args.base_url, cases.get("related", []), args.timeout)
        rows_by_type["timeliness"] = evaluate_qa(client, args.base_url, cases.get("timeliness", []), "timeliness", args.timeout)
        rows_by_type["ocr"] = evaluate_qa(client, args.base_url, cases.get("ocr", []), "ocr", args.timeout)

    output = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "summary": {name: score_rows(rows) for name, rows in rows_by_type.items()},
        "details": rows_by_type,
    }

    output_json = (root / args.output_json).resolve()
    output_md = (root / args.output_md).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(output), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
