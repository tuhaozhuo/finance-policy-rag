# API 性能基线报告

- 运行时间: 2026-04-08T11:20:00
- 基准地址: http://127.0.0.1:8000/api/v1
- 时延目标: <= 2000.0 ms（avg 与 p95）

## /search
- total: 5
- success: 5
- success_rate: 1.0
- avg_ms: 108.39
- p50_ms: 53.01
- p95_ms: 80.39
- max_ms: 348.54
- target: PASS

## /qa
- total: 5
- success: 5
- success_rate: 1.0
- avg_ms: 45.59
- p50_ms: 46.61
- p95_ms: 50.54
- max_ms: 54.81
- target: PASS

## /search/related
- total: 3
- success: 3
- success_rate: 1.0
- avg_ms: 54.15
- p50_ms: 53.44
- p95_ms: 53.44
- max_ms: 66.36
- target: PASS