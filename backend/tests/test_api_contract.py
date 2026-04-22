from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_contract() -> None:
    response = client.post(
        "/api/v1/search",
        json={
            "query": "票据业务监管要求",
            "region": "上海",
            "source_org": "上海监管局",
            "category": "规范性文件",
            "status": "effective",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "citations" in payload["data"]
    assert "keyword_candidates" in payload["data"]
    assert "vector_candidates" in payload["data"]
    assert "reranked_candidates" in payload["data"]


def test_qa_contract() -> None:
    response = client.post(
        "/api/v1/qa",
        json={
            "question": "银行承兑汇票业务有哪些重点监管要求？",
            "region": "上海",
            "source_org": "上海监管局",
            "category": "规范性文件",
            "include_expired": False,
            "top_k": 3,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload["data"]
    assert "confidence_score" in payload["data"]
    assert "consistency_score" in payload["data"]
    assert 0.0 <= payload["data"]["consistency_score"] <= 1.0


def test_upload_contract() -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sample.docx", BytesIO(b"dummy"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["doc_id"].startswith("doc-")
    assert payload["data"]["stored_path"].endswith("sample.docx")
    assert payload["data"]["doc_id"] in payload["data"]["stored_path"]


def test_upload_same_filename_uses_unique_paths() -> None:
    first = client.post(
        "/api/v1/documents/upload",
        files={"file": ("same.txt", BytesIO("第一条 同名文件一".encode("utf-8")), "text/plain")},
    )
    second = client.post(
        "/api/v1/documents/upload",
        files={"file": ("same.txt", BytesIO("第一条 同名文件二".encode("utf-8")), "text/plain")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["doc_id"] != second_data["doc_id"]
    assert first_data["stored_path"] != second_data["stored_path"]


def test_ingest_contract() -> None:
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sample.txt", BytesIO("第一条 本办法适用于示例场景。".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["data"]["doc_id"]

    ingest = client.post("/api/v1/documents/ingest", json={"doc_id": doc_id, "force_reindex": True})
    assert ingest.status_code == 200
    data = ingest.json()["data"]
    assert data["doc_id"] == doc_id
    assert data["chunks_created"] >= 1

    search = client.post(
        "/api/v1/search",
        json={
            "query": "示例场景",
            "status": "effective",
            "top_k": 3,
        },
    )
    assert search.status_code == 200
    search_data = search.json()["data"]
    assert search_data["reranked_candidates"] >= 1
    assert search_data["citations"][0]["retrieval_score"] is not None

    related = client.post(
        "/api/v1/search/related",
        json={
            "query": "示例场景",
            "doc_id": doc_id,
            "top_k": 3,
            "neighbor_window": 2,
        },
    )
    assert related.status_code == 200
    related_data = related.json()["data"]
    assert "anchor_citations" in related_data
    assert "related_citations" in related_data


def test_related_contract_validation() -> None:
    response = client.post(
        "/api/v1/search/related",
        json={
            "status": "effective",
            "top_k": 3,
            "neighbor_window": 2,
        },
    )
    assert response.status_code == 400


def test_ingest_task_queue_contract() -> None:
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("task.txt", BytesIO("第一条 任务队列测试条文。".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["data"]["doc_id"]

    create = client.post(
        "/api/v1/documents/ingest/tasks",
        json={"doc_ids": [doc_id], "force_reindex": True, "max_attempts": 2},
    )
    assert create.status_code == 200
    create_data = create.json()["data"]
    assert create_data["created_count"] == 1

    run = client.post("/api/v1/documents/ingest/tasks/run", json={"limit": 10, "ignore_schedule": True})
    assert run.status_code == 200
    run_data = run.json()["data"]
    assert run_data["processed"] >= 1

    tasks = client.get("/api/v1/documents/ingest/tasks?limit=20")
    assert tasks.status_code == 200
    rows = tasks.json()["data"]
    assert isinstance(rows, list)
    assert any(item["doc_id"] == doc_id for item in rows)
    matched = [item for item in rows if item["doc_id"] == doc_id]
    assert matched[0]["current_stage"] in {"completed", "running", None}
    assert isinstance(matched[0]["stage_metrics"], dict)


def test_document_tags_management_contract() -> None:
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("tags.txt", BytesIO("第一条 标签管理测试".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["data"]["doc_id"]

    update = client.patch(
        f"/api/v1/documents/{doc_id}/tags",
        json={"tags": ["票据", "监管", "票据", " "]},
    )
    assert update.status_code == 200
    tags = update.json()["data"]["tags"]
    assert tags == ["票据", "监管"]

    listing = client.get("/api/v1/documents/tags")
    assert listing.status_code == 200
    rows = listing.json()["data"]
    assert any(item["tag"] == "票据" for item in rows)


def test_qa_effective_fallback_to_expired() -> None:
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("已废止示例制度.txt", BytesIO("第一条 本条文用于失效制度回退测试。".encode("utf-8")), "text/plain")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["data"]["doc_id"]

    ingest = client.post("/api/v1/documents/ingest", json={"doc_id": doc_id, "force_reindex": True})
    assert ingest.status_code == 200

    qa = client.post(
        "/api/v1/qa",
        json={
            "question": "失效制度回退测试有哪些要求？",
            "include_expired": False,
            "top_k": 3,
        },
    )
    assert qa.status_code == 200
    data = qa.json()["data"]
    assert "历史/失效条文" in data["effective_status_summary"] or "未检索到可用条文" in data["effective_status_summary"]


def test_history_and_favorites_are_persistent_contracts() -> None:
    history = client.post(
        "/api/v1/history",
        json={"user_id": "u-persist", "query_text": "持久化历史测试", "query_type": "keyword"},
    )
    assert history.status_code == 200

    history_list = client.get("/api/v1/history?user_id=u-persist")
    assert history_list.status_code == 200
    assert any(item["query_text"] == "持久化历史测试" for item in history_list.json()["data"])

    favorite = client.post(
        "/api/v1/favorites",
        json={"user_id": "u-persist", "doc_id": "doc-test", "article_no": "第一条", "note": "收藏测试"},
    )
    assert favorite.status_code == 200

    favorite_list = client.get("/api/v1/favorites?user_id=u-persist")
    assert favorite_list.status_code == 200
    assert any(item["doc_id"] == "doc-test" for item in favorite_list.json()["data"])


def test_qa_record_is_persisted_to_history() -> None:
    qa = client.post(
        "/api/v1/qa",
        json={
            "question": "示例场景有什么要求？",
            "user_id": "u-qa",
            "session_id": "s-qa",
            "include_expired": False,
            "top_k": 3,
        },
    )
    assert qa.status_code == 200
    qa_data = qa.json()["data"]
    assert qa_data["qa_record_id"]

    history_list = client.get("/api/v1/history?user_id=u-qa")
    assert history_list.status_code == 200
    assert any(item["history_id"] == qa_data["qa_record_id"] for item in history_list.json()["data"])
