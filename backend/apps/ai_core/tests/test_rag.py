"""RAG 服务测试：分块边界、哈希嵌入、索引/检索/统计（无 chromadb）。"""

from __future__ import annotations

import math

from django.test import TestCase

from apps.ai_core.models import RAGConfiguration
from apps.ai_core.services.rag_service import RAGService, embed_text, split_text
from apps.ai_core.tests.helpers import TempMediaMixin, create_project, create_user
from apps.common.api.api_exception_handler import BusinessError
from apps.projects.models import KnowledgeDocument


class SplitTextTests(TestCase):
    def test_empty_and_short_inputs(self):
        self.assertEqual(split_text("", 100, 10), [])
        self.assertEqual(split_text(None, 100, 10), [])
        self.assertEqual(split_text("   \n\t ", 100, 10), [])
        self.assertEqual(split_text("hello", 100, 10), ["hello"])
        self.assertEqual(split_text("  hello  ", 100, 10), ["hello"])

    def test_windows_and_overlap(self):
        chunks = split_text("abcdefghij", 5, 2)
        self.assertEqual(chunks, ["abcde", "defgh", "ghij"])
        long_chunks = split_text("x" * 2500, 1000, 200)
        self.assertEqual(len(long_chunks), 3)
        self.assertEqual([len(chunk) for chunk in long_chunks], [1000, 1000, 900])

    def test_overlap_larger_than_chunk_size_still_progresses(self):
        chunks = split_text("a" * 30, 10, 99)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))

    def test_invalid_chunk_size_raises(self):
        with self.assertRaises(BusinessError) as ctx:
            split_text("abc", 0, 0)
        self.assertEqual(ctx.exception.biz_code, "invalid_chunk_config")


class EmbeddingTests(TestCase):
    def test_embedding_is_deterministic_and_normalised(self):
        first = embed_text("用户登录接口 token")
        second = embed_text("用户登录接口 token")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        norm = math.sqrt(sum(value * value for value in first))
        self.assertAlmostEqual(norm, 1.0, places=4)
        self.assertEqual(embed_text(""), [0.0] * 64)
        self.assertNotEqual(first, embed_text("完全无关的订单内容"))


class RAGServiceTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user("rag-user")
        self.project = create_project(self.user, name="RAG 知识库")
        self.document = KnowledgeDocument.objects.create(
            project=self.project,
            title="登录接口说明",
            content=(
                "用户登录接口使用 POST /api/login，参数为 username 与 password。"
                "登录成功后返回 token，后续请求需要携带 Authorization 头。"
            ),
        )
        self.other_document = KnowledgeDocument.objects.create(
            project=self.project,
            title="订单接口说明",
            content="创建订单接口使用 POST /api/orders，需要 sku_id 与 quantity 参数。",
        )
        self.service = RAGService()

    def test_index_updates_document_and_stats(self):
        chunk_count = self.service.index_document(self.document)
        self.assertGreaterEqual(chunk_count, 1)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, "indexed")
        self.assertEqual(self.document.chunk_count, chunk_count)
        self.assertIsNotNone(self.document.indexed_at)

        self.service.index_document(self.other_document)
        stats = self.service.stats()
        self.assertEqual(stats["documents"], 2)
        self.assertGreaterEqual(stats["chunks"], 2)
        self.assertIn("project_", stats["collection"])

    def test_search_returns_ranked_deterministic_hits(self):
        self.service.index_document(self.document)
        self.service.index_document(self.other_document)
        hits = self.service.search("登录 token", project=self.project, top_k=5)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["source"], "登录接口说明")
        self.assertIn("登录", hits[0]["text"])
        self.assertEqual(
            list(hits[0].keys()), ["text", "score", "source", "document_id"]
        )
        self.assertGreaterEqual(hits[0]["score"], hits[-1]["score"])
        self.assertEqual(
            [hit["text"] for hit in hits], [hit["text"] for hit in self.service.search("登录 token", project=self.project, top_k=5)]
        )

        top_one = self.service.search("登录 token", project=self.project, top_k=1)
        self.assertEqual(len(top_one), 1)
        self.assertEqual(top_one[0]["text"], hits[0]["text"])

    def test_search_without_match_or_query_is_empty(self):
        self.service.index_document(self.document)
        self.assertEqual(self.service.search("", project=self.project), [])
        self.assertEqual(
            self.service.search("zzzzquux-nope", project=self.project), []
        )

    def test_reindex_replaces_chunks(self):
        first = self.service.index_document(self.document)
        second = self.service.index_document(self.document)
        self.assertEqual(first, second)
        stats = self.service.stats()
        self.assertEqual(stats["documents"], 1)
        self.assertEqual(stats["chunks"], second)

    def test_chunk_configuration_is_applied(self):
        RAGConfiguration.objects.create(
            project=self.project,
            name="small-chunks",
            chunk_size=20,
            chunk_overlap=5,
            is_default=True,
        )
        document = KnowledgeDocument.objects.create(
            project=self.project,
            title="长文档",
            content="接口参数校验。" * 20,
        )
        chunk_count = RAGService().index_document(document)
        self.assertGreater(chunk_count, 1)
        document.refresh_from_db()
        self.assertEqual(document.chunk_count, chunk_count)
        hits = RAGService().search("接口参数", project=self.project, top_k=50)
        self.assertTrue(hits)
        self.assertTrue(all(len(hit["text"]) <= 20 for hit in hits))

    def test_index_empty_document_falls_back_to_title(self):
        document = KnowledgeDocument.objects.create(
            project=self.project, title="空文档", content="   "
        )
        chunk_count = self.service.index_document(document)
        self.assertEqual(chunk_count, 1)  # title is still searchable
        document.refresh_from_db()
        self.assertEqual(document.status, "indexed")
        self.assertEqual(document.chunk_count, 1)

        empty = KnowledgeDocument.objects.create(
            project=self.project, title="", content=""
        )
        self.assertEqual(self.service.index_document(empty), 0)
