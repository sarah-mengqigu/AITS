"""RAG 检索服务（无 chromadb 也必须可用）。

实现要点
--------
* 分块：``split_text(text, chunk_size, overlap)`` 固定窗口切块（确定性）。
* 嵌入：**确定性本地哈希嵌入**（sha256 → 64 维浮点向量 → L2 归一化），
  不依赖任何模型/网络，同输入永远同输出。
* 存储：默认写入 ``settings.MEDIA_ROOT/rag/<collection>.json``（原子写），
  若 ``chromadb`` 可 import 且配置 ``vector_store=chroma`` 则优先使用。
* 检索：余弦相似度（向量已归一化，等价点积）排序，稳定 tie-break。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.common.api.api_exception_handler import BusinessError

logger = logging.getLogger(__name__)

EMBED_DIM = 64
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
_COLLECTION_SAFE_RE = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff-]+")
_TOKEN_RE = re.compile(r"[0-9A-Za-z_]+|[\u4e00-\u9fff]")


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def split_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split ``text`` into deterministic windows of at most ``chunk_size`` chars.

    * empty / whitespace only -> ``[]``
    * ``overlap >= chunk_size`` is clamped so the window always advances
    * ``chunk_size <= 0`` raises ``BusinessError(code="invalid_chunk_config")``
    """
    if text is None:
        return []
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return []
    try:
        size = int(chunk_size)
    except (TypeError, ValueError) as exc:
        raise BusinessError(
            message="chunk_size 必须为正整数", code="invalid_chunk_config"
        ) from exc
    if size <= 0:
        raise BusinessError(message="chunk_size 必须为正整数", code="invalid_chunk_config")
    try:
        overlap_value = int(overlap or 0)
    except (TypeError, ValueError):
        overlap_value = 0
    overlap_value = max(0, min(overlap_value, size - 1))
    step = size - overlap_value
    if step <= 0:  # pragma: no cover - defensive, overlap is already clamped
        step = size

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start += step
    return chunks


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic local hash embedding, L2 normalised.

    Each token is hashed to ``dim`` buckets with signed contributions, so the
    same token always lands on the same buckets regardless of its position
    (that is what makes cosine similarity meaningful for retrieval).
    """
    vector = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for offset in range(0, 16, 2):
            value = int.from_bytes(digest[offset : offset + 2], "big")
            index = value % dim
            sign = 1.0 if (value >> 15) & 1 else -1.0
            vector[index] += sign
    norm = math.sqrt(sum(component * component for component in vector))
    if norm <= 0:
        return vector
    return [round(component / norm, 10) for component in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))


def safe_collection_name(name: str) -> str:
    cleaned = _COLLECTION_SAFE_RE.sub("_", (name or "").strip()).strip("_")
    return cleaned[:96] or "global"


class RAGService:
    """Index / search knowledge documents for one project (or globally)."""

    def __init__(self, project=None, config=None):
        self.project = project
        self.config = config

    # ------------------------------------------------------------------
    # configuration helpers
    # ------------------------------------------------------------------
    @property
    def rag_dir(self) -> Path:
        root = Path(getattr(settings, "MEDIA_ROOT", Path("media")))
        directory = root / "rag"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def get_config(self, project=None):
        project = project if project is not None else self.project
        if self.config is not None and getattr(self.config, "project_id", None) in (
            None,
            getattr(project, "id", None),
        ):
            return self.config
        try:
            from apps.ai_core.models import RAGConfiguration

            queryset = RAGConfiguration.objects.all()
            if project is not None:
                config = queryset.filter(project=project, is_default=True).first()
                if config is not None:
                    return config
                config = queryset.filter(project=project).order_by("-updated_at", "-id").first()
                if config is not None:
                    return config
            config = queryset.filter(project__isnull=True, is_default=True).first()
            if config is not None:
                return config
            return queryset.filter(project__isnull=True).order_by("-updated_at", "-id").first()
        except Exception as exc:  # pragma: no cover - DB may be unavailable in scripts
            logger.warning("cannot load RAGConfiguration: %s", exc)
            return None

    def collection_name(self, project=None, config=None) -> str:
        project = project if project is not None else self.project
        config = config or self.config or self.get_config(project)
        configured = getattr(config, "collection_name", "") if config else ""
        if configured:
            return safe_collection_name(configured)
        if project is not None and getattr(project, "id", None) is not None:
            return safe_collection_name(f"project_{project.id}")
        return "global"

    def chunk_params(self, config=None) -> tuple[int, int]:
        config = config or self.config or self.get_config(self.project)
        size = int(getattr(config, "chunk_size", DEFAULT_CHUNK_SIZE) or DEFAULT_CHUNK_SIZE)
        overlap = int(
            getattr(config, "chunk_overlap", DEFAULT_CHUNK_OVERLAP)
            if config is not None
            else DEFAULT_CHUNK_OVERLAP
        )
        return size, max(0, min(overlap, size - 1))

    # ------------------------------------------------------------------
    # storage (JSON fallback)
    # ------------------------------------------------------------------
    def _collection_path(self, collection: str) -> Path:
        return self.rag_dir / f"{safe_collection_name(collection)}.json"

    def _empty_store(self, collection: str) -> dict:
        return {"collection": collection, "dim": EMBED_DIM, "documents": {}}

    def _load_store(self, collection: str) -> dict:
        path = self._collection_path(collection)
        if not path.exists():
            return self._empty_store(collection)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("corrupt rag store %s: %s", path, exc)
            return self._empty_store(collection)
        if not isinstance(data, dict) or not isinstance(data.get("documents"), dict):
            return self._empty_store(collection)
        data.setdefault("collection", collection)
        return data

    def _write_store(self, collection: str, data: dict) -> None:
        path = self._collection_path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=".rag-", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except OSError:  # pragma: no cover
                    pass

    # ------------------------------------------------------------------
    # chroma (optional)
    # ------------------------------------------------------------------
    @staticmethod
    def chroma_available() -> bool:
        try:
            import chromadb  # noqa: F401

            return True
        except Exception:  # pragma: no cover - chromadb is optional
            return False

    def _use_chroma(self, config) -> bool:
        if getattr(config, "vector_store", "") != "chroma":
            return False
        return self.chroma_available()

    def _chroma_collection(self, collection: str):
        import chromadb

        client = chromadb.PersistentClient(path=str(self.rag_dir / "chroma"))
        return client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def _chroma_index(self, collection: str, document, chunks: list[str],
                      embeddings: list[list[float]]) -> int:
        store = self._chroma_collection(collection)
        doc_id = str(getattr(document, "id", "") or getattr(document, "pk", ""))
        try:  # drop stale chunks of this document
            store.delete(where={"document_id": doc_id})
        except Exception:  # pragma: no cover - collection may be empty
            pass
        if not chunks:
            return 0
        store.upsert(
            ids=[f"{doc_id}:{index}" for index in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": doc_id,
                    "source": getattr(document, "title", "") or "",
                    "project_id": str(getattr(document, "project_id", "") or ""),
                }
                for _ in chunks
            ],
        )
        return len(chunks)

    def _chroma_search(self, collection: str, query: str, top_k: int) -> list[dict]:
        store = self._chroma_collection(collection)
        result = store.query(query_embeddings=[embed_text(query)], n_results=max(1, top_k))
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            distance = distances[index] if index < len(distances) else 1.0
            hits.append(
                {
                    "text": text,
                    "score": round(1.0 - float(distance), 6),
                    "source": (metadata or {}).get("source", ""),
                    "document_id": int((metadata or {}).get("document_id") or 0),
                }
            )
        return hits

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def index_document(self, document) -> int:
        """Chunk + embed + persist one ``KnowledgeDocument``; returns chunk count."""
        if document is None:
            raise BusinessError(message="文档不能为空", code="invalid_document")
        project = getattr(document, "project", None)
        config = self.config or self.get_config(project)
        collection = self.collection_name(project=project, config=config)
        size, overlap = self.chunk_params(config)
        text = (getattr(document, "content", "") or "").strip() or (getattr(document, "title", "") or "")
        try:
            chunks = split_text(text, size, overlap)
            embeddings = [embed_text(chunk) for chunk in chunks]

            if self._use_chroma(config):
                try:
                    count = self._chroma_index(collection, document, chunks, embeddings)
                    self._finalize_document(document, count)
                    return count
                except Exception as exc:  # pragma: no cover - optional backend
                    logger.warning("chroma indexing failed, falling back to json: %s", exc)

            store = self._load_store(collection)
            doc_id = str(getattr(document, "id", "") or getattr(document, "pk", ""))
            store["documents"][doc_id] = {
                "document_id": int(getattr(document, "id", 0) or 0),
                "source": getattr(document, "title", "") or "",
                "project_id": getattr(document, "project_id", None),
                "indexed_at": timezone.now().isoformat(),
                "chunks": [
                    {
                        "id": f"{doc_id}:{index}",
                        "text": chunk,
                        "embedding": embeddings[index],
                    }
                    for index, chunk in enumerate(chunks)
                ],
            }
            self._write_store(collection, store)
        except BusinessError:
            self._mark_failed(document, "索引失败：分块配置非法")
            raise
        except Exception as exc:
            logger.exception("index_document failed")
            self._mark_failed(document, str(exc))
            raise BusinessError(message=f"索引失败: {exc}", code="index_failed") from exc

        self._finalize_document(document, len(chunks))
        return len(chunks)

    def _persist_state(self, document, values: dict) -> None:
        """Persist index state without mutating the caller's instance.

        ``apps.projects.views`` indexes a freshly created document inside
        ``perform_create`` and then serialises the same instance; keeping the
        in-memory object untouched avoids leaking our side effect into their
        response payload. Callers that want the new state use ``refresh_from_db``.
        """
        pk = getattr(document, "pk", None)
        if pk is None:  # unsaved / plain object: best effort attribute assignment
            for key, value in values.items():
                setattr(document, key, value)
            try:  # pragma: no cover - only for unsaved instances
                document.save()
            except Exception:
                logger.warning("cannot persist index state on unsaved document")
            return
        try:
            type(document).objects.filter(pk=pk).update(**values)
        except Exception:  # pragma: no cover - DB may be unavailable
            logger.warning("cannot update document index state", exc_info=True)

    def _finalize_document(self, document, chunk_count: int) -> None:
        now = timezone.now()
        self._persist_state(
            document,
            {
                "status": "indexed",
                "chunk_count": int(chunk_count),
                "indexed_at": now,
                "error_message": "",
                "updated_at": now,
            },
        )

    def _mark_failed(self, document, message: str) -> None:
        self._persist_state(
            document,
            {
                "status": "failed",
                "error_message": str(message)[:2000],
                "updated_at": timezone.now(),
            },
        )

    def search(self, query: str, project=None, top_k: int = 5) -> list[dict]:
        """Cosine similarity search over the project collection; deterministic."""
        project = project if project is not None else self.project
        if not query or not str(query).strip():
            return []
        try:
            limit = int(top_k)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 50))
        config = self.config or self.get_config(project)
        collection = self.collection_name(project=project, config=config)

        if self._use_chroma(config):
            try:
                return self._chroma_search(collection, str(query), limit)
            except Exception as exc:  # pragma: no cover - optional backend
                logger.warning("chroma search failed, falling back to json: %s", exc)

        store = self._load_store(collection)
        query_vector = embed_text(str(query))
        query_tokens = set(tokenize(str(query)))
        scored: list[dict] = []
        for doc_id, document in (store.get("documents") or {}).items():
            for chunk in document.get("chunks") or []:
                chunk_text = chunk.get("text", "")
                # Cheap lexical gate keeps "no match" deterministic (hash vectors
                # alone could collide in a 64-dim space).
                if query_tokens and not (query_tokens & set(tokenize(chunk_text))):
                    continue
                score = cosine_similarity(query_vector, chunk.get("embedding") or [])
                if score <= 0:
                    continue
                scored.append(
                    {
                        "text": chunk_text,
                        "score": round(score, 6),
                        "source": document.get("source", ""),
                        "document_id": int(document.get("document_id") or doc_id or 0),
                    }
                )
        scored.sort(key=lambda item: (-item["score"], item["document_id"], item["text"]))
        return scored[:limit]

    def stats(self) -> dict:
        """Aggregate chunk/document counters over every local collection."""
        documents = 0
        chunks = 0
        collections: list[str] = []
        try:
            files = sorted(self.rag_dir.glob("*.json"))
        except OSError:  # pragma: no cover
            files = []
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            collections.append(data.get("collection") or path.stem)
            for document in (data.get("documents") or {}).values():
                documents += 1
                chunks += len(document.get("chunks") or [])
        if not collections:
            collection = "default"
        elif len(collections) == 1:
            collection = collections[0]
        else:
            collection = "all"
        return {"documents": documents, "chunks": chunks, "collection": collection}

    def remove_document(self, document) -> None:
        """Drop one document's chunks from the local collection."""
        if document is None:
            return
        project = getattr(document, "project", None)
        collection = self.collection_name(project=project)
        store = self._load_store(collection)
        doc_id = str(getattr(document, "id", "") or getattr(document, "pk", ""))
        if doc_id in (store.get("documents") or {}):
            store["documents"].pop(doc_id, None)
            self._write_store(collection, store)
