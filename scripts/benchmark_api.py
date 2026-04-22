#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path
from time import perf_counter

import httpx


DEFAULT_SEARCH_QUERIES = [
    "票据业务监管要求",
    "保险销售行为可回溯",
    "消费者权益保护要求",
    "绿色金融指导意见",
    "小微企业金融服务",
]

DEFAULT_QA_QUERIES = [
    "银行承兑汇票业务有哪些重点监管要求？",
    "人身保险销售行为可回溯的核心要求是什么？",
    "如何理解监管文件中的消费者权益保护机制？",
    "绿色金融相关制度对银行提出了哪些约束？",
    "针对小微企业金融服务，监管最关注哪些风险点？",
]

DEFAULT_RELATED_QUERIES = [
    "票据业务",
    "消费者权益保护",
    "绿色金融",
]


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * ratio)
    return sorted_values[idx]


def run_case(client: httpx.Client, method: str, url: str, payload: dict, timeout: float) -> tuple[bool, float, int, str]:
    start = perf_counter()
    try:
        if method == "POST":
            response = client.post(url, json=payload, timeout=timeout)
        else:
            response = client.get(url, params=payload, timeout=timeout)
        latency_ms = (perf_counter() - start) * 1000
        ok = response.status_code == 200
        detail = ""
        if not ok:
            detail = response.text[:200]
        return ok, latency_ms, response.status_code, detail
    except Exception as exc:  # pragma: no cover
        latency_ms = (perf_counter() - start) * 1000
        return False, latency_ms, -1, str(exc)


def summarize(rows: list[tuple[bool, float, int, str]]) -> dict[str, float | int]:
    if not rows:
        return {
            "total": 0,
            "success": 0,
            "success_rate": 0.0,
            "avg_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }

    latencies = [item[1] for item in rows]
    success = sum(1 for item in rows if item[0])
    total = len(rows)

    return {
        "total": total,
        "success": success,
        "success_rate": round(success / total, 4),
        "avg_ms": round(statistics.mean(latencies), 2),
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "max_ms": round(max(latencies), 2),
    }


def load_query_sets(path: Path | None) -> tuple[list[str], list[str], list[str]]:
    if path is None or not path.exists():
        return DEFAULT_SEARCH_QUERIES, DEFAULT_QA_QUERIES, DEFAULT_RELATED_QUERIES

    data = json.loads(path.read_text(encoding="utf-8"))
    search_queries = data.get("search", DEFAULT_SEARCH_QUERIES)
    qa_queries = data.get("qa", DEFAULT_QA_QUERIES)
    related_queries = data.get("related", DEFAULT_RELATED_QUERIES)
    return list(search_queries), list(qa_queries), list(related_queries)


def _target_flag(summary: dict, target_ms: float) -> str:
    avg_ok = float(summary["avg_ms"]) <= target_ms
    p95_ok = float(summary["p95_ms"]) <= target_ms
    return "PASS" if avg_ok and p95_ok else "FAIL"


def render_markdown(base_url: str, search_summary: dict, qa_summary: dict, related_summary: dict, run_at: str, target_ms: float) -> str:
    return "\n".join(
        [
            "# API 性能基线报告",
            "",
            f"- 运行时间: {run_at}",
            f"- 基准地址: {base_url}",
            f"- 时延目标: <= {target_ms} ms（avg 与 p95）",
            "",
            "## /search",
            f"- total: {search_summary['total']}",
            f"- success: {search_summary['success']}",
            f"- success_rate: {search_summary['success_rate']}",
            f"- avg_ms: {search_summary['avg_ms']}",
            f"- p50_ms: {search_summary['p50_ms']}",
            f"- p95_ms: {search_summary['p95_ms']}",
            f"- max_ms: {search_summary['max_ms']}",
            f"- target: {_target_flag(search_summary, target_ms)}",
            "",
            "## /qa",
            f"- total: {qa_summary['total']}",
            f"- success: {qa_summary['success']}",
            f"- success_rate: {qa_summary['success_rate']}",
            f"- avg_ms: {qa_summary['avg_ms']}",
            f"- p50_ms: {qa_summary['p50_ms']}",
            f"- p95_ms: {qa_summary['p95_ms']}",
            f"- max_ms: {qa_summary['max_ms']}",
            f"- target: {_target_flag(qa_summary, target_ms)}",
            "",
            "## /search/related",
            f"- total: {related_summary['total']}",
            f"- success: {related_summary['success']}",
            f"- success_rate: {related_summary['success_rate']}",
            f"- avg_ms: {related_summary['avg_ms']}",
            f"- p50_ms: {related_summary['p50_ms']}",
            f"- p95_ms: {related_summary['p95_ms']}",
            f"- max_ms: {related_summary['max_ms']}",
            f"- target: {_target_flag(related_summary, target_ms)}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark /search, /qa and /search/related latency")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="API base URL")
    parser.add_argument("--query-file", default="", help="JSON file: {\"search\":[],\"qa\":[],\"related\":[]}")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--target-ms", type=float, default=2000.0, help="latency target in milliseconds")
    parser.add_argument("--output-json", default="docs/reports/perf_baseline.json")
    parser.add_argument("--output-md", default="docs/reports/perf_baseline.md")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    query_file = Path(args.query_file).resolve() if args.query_file else None
    search_queries, qa_queries, related_queries = load_query_sets(query_file)

    search_rows: list[tuple[bool, float, int, str]] = []
    qa_rows: list[tuple[bool, float, int, str]] = []
    related_rows: list[tuple[bool, float, int, str]] = []

    with httpx.Client() as client:
        for query in search_queries:
            payload = {"query": query, "status": "effective", "top_k": 5}
            search_rows.append(run_case(client, "POST", f"{args.base_url}/search", payload, args.timeout))

        for question in qa_queries:
            payload = {"question": question, "include_expired": False, "top_k": 5}
            qa_rows.append(run_case(client, "POST", f"{args.base_url}/qa", payload, args.timeout))

        for query in related_queries:
            payload = {"query": query, "status": "effective", "top_k": 5, "neighbor_window": 2}
            related_rows.append(run_case(client, "POST", f"{args.base_url}/search/related", payload, args.timeout))

    search_summary = summarize(search_rows)
    qa_summary = summarize(qa_rows)
    related_summary = summarize(related_rows)

    target_passed = (
        _target_flag(search_summary, args.target_ms) == "PASS"
        and _target_flag(qa_summary, args.target_ms) == "PASS"
        and _target_flag(related_summary, args.target_ms) == "PASS"
    )

    run_at = datetime.now().isoformat(timespec="seconds")
    output = {
        "run_at": run_at,
        "base_url": args.base_url,
        "target_ms": args.target_ms,
        "target_passed": target_passed,
        "search": search_summary,
        "qa": qa_summary,
        "related": related_summary,
        "search_failures": [
            {"status": row[2], "detail": row[3]} for row in search_rows if not row[0]
        ],
        "qa_failures": [
            {"status": row[2], "detail": row[3]} for row in qa_rows if not row[0]
        ],
        "related_failures": [
            {"status": row[2], "detail": row[3]} for row in related_rows if not row[0]
        ],
    }

    output_json = (root / args.output_json).resolve()
    output_md = (root / args.output_md).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(
        render_markdown(args.base_url, search_summary, qa_summary, related_summary, run_at, args.target_ms),
        encoding="utf-8",
    )

    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"report_json={output_json}")
    print(f"report_md={output_md}")


if __name__ == "__main__":
    main()
