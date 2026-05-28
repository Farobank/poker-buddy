"""theory_lookup — BM25 over the curated theory corpus.

Indexes every markdown file in theory/ (and symlinks like strategy-notes.md
which points at hu-poker-trainer's STRATEGY_NOTES). Splits each file into
~400-word chunks. Returns the top-k chunks with title + source + a short
quote so the LLM can ground its reasoning and cite the source aloud.

The index is built once on first call and cached in module state. If theory/
changes between runs, restart the server (cheap).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

DEFAULT_THEORY_DIR = Path(__file__).resolve().parent.parent.parent / "theory"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_CHUNK_TARGET_WORDS = 400


@dataclass
class Chunk:
    """A single retrievable chunk of theory text."""
    path: str          # filename only
    title: str         # from frontmatter or first H1
    source: str        # from frontmatter; cited verbatim
    tags: list[str]
    text: str
    tokens: list[str]


class _Index:
    """Lazy BM25 index over the theory corpus."""

    def __init__(self, theory_dir: Path):
        self.theory_dir = theory_dir
        self._chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None

    def build(self) -> None:
        chunks: list[Chunk] = []
        for path in sorted(self.theory_dir.glob("*.md")):
            try:
                text = path.read_text()
            except OSError:
                continue
            for c in _split_into_chunks(path, text):
                chunks.append(c)
        if not chunks:
            self._chunks = []
            self._bm25 = None
            return
        self._chunks = chunks
        self._bm25 = BM25Okapi([c.tokens for c in chunks])

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        if self._bm25 is None:
            self.build()
        if self._bm25 is None or not self._chunks:
            return []
        q_tokens = _tokenize(query)
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(
            zip(self._chunks, scores, strict=True),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(c, float(s)) for c, s in ranked[:k] if s > 0]


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Extract --- frontmatter --- block. Returns (meta, body)."""
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    block = m.group(1)
    body = raw[m.end():]
    meta: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key.strip()] = [s.strip() for s in val[1:-1].split(",") if s.strip()]
        else:
            meta[key.strip()] = val.strip().strip('"')
    return meta, body


def _split_into_chunks(path: Path, raw: str) -> list[Chunk]:
    meta, body = _parse_frontmatter(raw)
    title = str(meta.get("title", "")).strip()
    if not title:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if not title:
            title = path.stem.replace("-", " ").title()
    source = str(meta.get("source", "")) or path.name
    tags = meta.get("tags", []) if isinstance(meta.get("tags"), list) else []

    words = body.split()
    chunks: list[Chunk] = []
    if len(words) <= _CHUNK_TARGET_WORDS:
        text = body.strip()
        if text:
            chunks.append(Chunk(
                path=path.name, title=title, source=source, tags=list(tags),
                text=text, tokens=_tokenize(text),
            ))
        return chunks

    for i in range(0, len(words), _CHUNK_TARGET_WORDS):
        text = " ".join(words[i : i + _CHUNK_TARGET_WORDS]).strip()
        if text:
            chunks.append(Chunk(
                path=path.name, title=title, source=source, tags=list(tags),
                text=text, tokens=_tokenize(text),
            ))
    return chunks


_index: _Index | None = None


def _get_index() -> _Index:
    global _index
    if _index is None:
        theory_dir = Path(os.environ.get("BUDDY_THEORY_DIR", DEFAULT_THEORY_DIR))
        _index = _Index(theory_dir)
        _index.build()
    return _index


def theory_lookup(query: str, k: int = 3) -> dict[str, Any]:
    """Return up to k cited chunks relevant to the query."""
    if not query or not query.strip():
        return {"data": [], "confidence": "yellow", "source": "theory_lookup", "note": "empty query"}
    hits = _get_index().search(query, k=max(1, k))
    chunks = [
        {
            "title": c.title,
            "source": c.source,
            "tags": c.tags,
            "excerpt": _excerpt(c.text, max_chars=600),
            "score": round(score, 3),
        }
        for c, score in hits
    ]
    return {
        "data": chunks,
        "confidence": "yellow",
        "source": "theory_lookup (BM25 over theory/)",
    }


def _excerpt(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    if last_period > max_chars * 0.6:
        return cut[: last_period + 1]
    return cut + "…"


def reset_index_for_tests() -> None:
    """Test hook — clears the cached index so a new theory_dir takes effect."""
    global _index
    _index = None
