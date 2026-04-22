from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


class MetadataExtractor:
    def extract(self, file_path: Path, title: str, text: str = "") -> dict[str, object]:
        parts = file_path.parts
        corpus = f"{title}\n{text[:8000]}"

        path_org = next((part for part in parts if "监管局" in part), None)
        body_org = self._extract_source_org(corpus)
        source_org = body_org or path_org
        category = file_path.parent.name if file_path.parent.name else None

        region = None
        if source_org and source_org.endswith("监管局"):
            region = source_org.replace("监管局", "")
        elif path_org and path_org.endswith("监管局"):
            region = path_org.replace("监管局", "")

        status, status_evidence = self._extract_status(corpus)
        document_number = self._extract_document_number(corpus)

        publish_date = self._extract_publish_date(corpus)
        effective_date = self._extract_effective_date(corpus)
        expire_date = self._extract_expire_date(corpus)

        tags = [item for item in [region, source_org, category, document_number] if item]
        evidence = {
            "source_org": body_org or path_org or "",
            "document_number": document_number or "",
            "publish_date": publish_date.isoformat() if publish_date else "",
            "effective_date": effective_date.isoformat() if effective_date else "",
            "expire_date": expire_date.isoformat() if expire_date else "",
            "status": status_evidence,
        }

        return {
            "source_org": source_org,
            "document_number": document_number,
            "region": region,
            "category": category,
            "status": status,
            "status_evidence": status_evidence,
            "publish_date": publish_date,
            "effective_date": effective_date,
            "expire_date": expire_date,
            "tags": tags,
            "metadata_evidence_json": json.dumps(evidence, ensure_ascii=False),
        }

    def _extract_date(self, text: str) -> datetime | None:
        match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
        if not match:
            return None
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            return None

    def _extract_publish_date(self, text: str) -> datetime | None:
        patterns = [
            r"(?:印发|发布|公布|通知).*?(20\d{2}年\d{1,2}月\d{1,2}日)",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)",
        ]
        return self._extract_date_by_patterns(text, patterns)

    def _extract_effective_date(self, text: str) -> datetime | None:
        patterns = [
            r"(?:自|于)(20\d{2}年\d{1,2}月\d{1,2}日)(?:起)?(?:施行|实施|执行|生效)",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)(?:起)?(?:施行|实施|执行|生效)",
        ]
        return self._extract_date_by_patterns(text, patterns)

    def _extract_expire_date(self, text: str) -> datetime | None:
        patterns = [
            r"(?:自|于)(20\d{2}年\d{1,2}月\d{1,2}日)(?:起)?(?:废止|失效|终止)",
            r"(20\d{2}年\d{1,2}月\d{1,2}日)(?:起)?(?:废止|失效|终止)",
        ]
        return self._extract_date_by_patterns(text, patterns)

    def _extract_date_by_patterns(self, text: str, patterns: list[str]) -> datetime | None:
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            date_text = match.group(1)
            parsed = self._extract_date(date_text)
            if parsed:
                return parsed
        return None

    def _extract_source_org(self, text: str) -> str | None:
        patterns = [
            r"(国家金融监督管理总局[\u4e00-\u9fff]{0,12}监管局)",
            r"(中国银保监会[\u4e00-\u9fff]{0,12}监管局)",
            r"(中国银监会[\u4e00-\u9fff]{0,12}监管局)",
            r"(中国保监会[\u4e00-\u9fff]{0,12}监管局)",
            r"([\u4e00-\u9fff]{2,8}(?:银保监局|银监局|保监局))",
            r"([\u4e00-\u9fff]{2,8}监管局)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_document_number(self, text: str) -> str | None:
        patterns = [
            r"([\u4e00-\u9fff]{1,8}(?:银保监|银监|保监|金规|金监)[\u4e00-\u9fff]{0,8}〔\d{4}〕\d+号)",
            r"([\u4e00-\u9fff]{1,12}发〔\d{4}〕\d+号)",
            r"(银保监办发〔\d{4}〕\d+号)",
            r"(银监办发〔\d{4}〕\d+号)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_status(self, text: str) -> tuple[str, str]:
        expired_patterns = [
            r"(?:本(?:办法|通知|规定|制度|文件)|该(?:办法|通知|规定|制度|文件)|原(?:办法|通知|规定|制度|文件)).{0,30}(?:废止|失效|停止执行|不再执行)",
            r"(?:废止|失效|停止执行|不再执行).{0,30}(?:本(?:办法|通知|规定|制度|文件)|该(?:办法|通知|规定|制度|文件)|原(?:办法|通知|规定|制度|文件))",
            r"(?:已被|予以).{0,20}(?:废止|失效|停止执行)",
        ]
        for pattern in expired_patterns:
            match = re.search(pattern, text)
            if match:
                return "expired", match.group(0)

        effective_patterns = [
            r"(?:自|于)?20\d{2}年\d{1,2}月\d{1,2}日(?:起)?(?:施行|实施|执行|生效)",
            r"(?:现予印发|印发给你们|请遵照执行|请认真贯彻执行)",
        ]
        for pattern in effective_patterns:
            match = re.search(pattern, text)
            if match:
                return "effective", match.group(0)

        return "unknown", "未识别到明确生效或失效依据"
