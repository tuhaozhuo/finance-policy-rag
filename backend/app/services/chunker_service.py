from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ChunkPiece:
    chapter: str | None
    article_no: str | None
    chunk_text: str
    keywords: list[str]


class Chunker:
    chapter_re = re.compile(r"^第[一二三四五六七八九十百千零〇0-9]+章")
    article_re = re.compile(r"^(第[一二三四五六七八九十百千零〇0-9]+条)")

    def __init__(self, max_chars: int = 500, overlap: int = 80) -> None:
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> list[ChunkPiece]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return []

        pieces = self._chunk_by_article(lines)
        if pieces:
            return pieces
        return self._chunk_by_window(text)

    def _chunk_by_article(self, lines: list[str]) -> list[ChunkPiece]:
        chunks: list[ChunkPiece] = []
        chapter: str | None = None
        article_no: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            if not buffer:
                return
            chunk_text = "\n".join(buffer).strip()
            if chunk_text:
                chunks.append(
                    ChunkPiece(
                        chapter=chapter,
                        article_no=article_no,
                        chunk_text=chunk_text,
                        keywords=self._extract_keywords(chunk_text),
                    )
                )

        for line in lines:
            if self.chapter_re.match(line):
                chapter = line.split(" ")[0]

            article_match = self.article_re.match(line)
            if article_match:
                flush()
                article_no = article_match.group(1)
                buffer = [line]
                continue

            if buffer:
                buffer.append(line)

        flush()
        return chunks

    def _chunk_by_window(self, text: str) -> list[ChunkPiece]:
        plain = re.sub(r"\s+", " ", text).strip()
        chunks: list[ChunkPiece] = []

        start = 0
        while start < len(plain):
            end = min(start + self.max_chars, len(plain))
            fragment = plain[start:end]
            chunks.append(
                ChunkPiece(
                    chapter=None,
                    article_no=None,
                    chunk_text=fragment,
                    keywords=self._extract_keywords(fragment),
                )
            )
            if end == len(plain):
                break
            start = max(0, end - self.overlap)

        return chunks

    def _extract_keywords(self, text: str) -> list[str]:
        candidates = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text)
        seen: set[str] = set()
        result: list[str] = []
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
            if len(result) >= 8:
                break
        return result
