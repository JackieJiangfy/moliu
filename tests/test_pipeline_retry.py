"""ChapterPipeline.run_with_retry 单测

验证质检不达标时的自动重试行为:
- 各 retry_on 条件触发正确
- 通过条件时不重试
- 重试次数限制
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from moliu.config import Config
from moliu.data.schemas import ChapterResult
from moliu.orchestrator.pipeline import ChapterPipeline, QualityReport


pytestmark = pytest.mark.asyncio


def _result(content: str = "test") -> ChapterResult:
    return ChapterResult(
        chapter_num=1,
        content=content,
        word_count=4,
        model_used="test-model",
        tokens_used=10,
    )


def _make_pipeline() -> ChapterPipeline:
    """构造一个不依赖外部依赖的 pipeline 实例"""
    cfg = Config()
    cfg.project_dir = None  # 防止误触文件 IO
    return ChapterPipeline(
        config=cfg,
        gateway=MagicMock(),
        prompts=MagicMock(),
    )


class TestRunWithRetry:
    """run_with_retry 各条件验证"""

    async def test_no_retry_when_quality_ok(self):
        """质检通过时不重试,只调用一次 generate_fn"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result()

        async def qual(_):
            qr = QualityReport()
            # 默认值: fatal=0, want_next=True, repetitive=False, tension=5
            return qr

        pipe = _make_pipeline()
        result, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=3,
            retry_on=("fatal", "reader", "tension_low", "repetitive"),
        )

        assert gen_calls == 1
        assert result.chapter_num == 1

    async def test_retry_on_fatal(self):
        """致命一致性问题触发重试"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result(f"v{gen_calls}")

        call_count = 0

        async def qual(_):
            nonlocal call_count
            call_count += 1
            qr = QualityReport()
            # 前 2 次有 fatal,第 3 次干净
            qr.consistency_fatal = 1 if call_count < 3 else 0
            return qr

        pipe = _make_pipeline()
        result, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=3,
            retry_on=("fatal",),
        )

        assert gen_calls == 3
        assert qr.consistency_fatal == 0
        assert "v3" in result.content

    async def test_retry_on_reader_not_want_next(self):
        """读者明确不想继续触发重试"""
        call_count = 0

        async def gen():
            nonlocal call_count
            call_count += 1
            return _result()

        qual_calls = 0

        async def qual(_):
            nonlocal qual_calls
            qual_calls += 1
            qr = QualityReport()
            qr.reader_want_next = qual_calls >= 2  # 第 1 次不想,第 2 次想
            return qr

        pipe = _make_pipeline()
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=2,
            retry_on=("reader",),
        )

        assert call_count == 2
        assert qr.reader_want_next is True

    async def test_retry_on_tension_low(self):
        """张力 < 4 触发重试"""
        call_count = 0

        async def gen():
            nonlocal call_count
            call_count += 1
            return _result()

        qual_calls = 0

        async def qual(_):
            nonlocal qual_calls
            qual_calls += 1
            qr = QualityReport()
            qr.tension_score = 3 if qual_calls < 2 else 6
            return qr

        pipe = _make_pipeline()
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=2,
            retry_on=("tension_low",),
        )

        assert call_count == 2
        assert qr.tension_score == 6

    async def test_retry_on_repetitive(self):
        """读者感觉重复触发重试"""
        call_count = 0

        async def gen():
            nonlocal call_count
            call_count += 1
            return _result()

        qual_calls = 0

        async def qual(_):
            nonlocal qual_calls
            qual_calls += 1
            qr = QualityReport()
            qr.reader_repetitive = qual_calls < 2
            return qr

        pipe = _make_pipeline()
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=2,
            retry_on=("repetitive",),
        )

        assert call_count == 2
        assert qr.reader_repetitive is False

    async def test_max_retries_limit(self):
        """达到 max_retries 上限后停止重试,返回最后一次结果"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result(f"v{gen_calls}")

        async def qual(_):
            qr = QualityReport()
            qr.consistency_fatal = 1  # 永远不达标
            return qr

        pipe = _make_pipeline()
        # max_retries=1 → 最多生成 2 次
        result, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=1,
            retry_on=("fatal",),
        )

        assert gen_calls == 2  # 初始 1 + 重试 1
        assert qr.consistency_fatal == 1  # 仍不达标,但已达到上限

    async def test_max_retries_zero(self):
        """max_retries=0 时不重试,即使质检失败"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result()

        async def qual(_):
            qr = QualityReport()
            qr.consistency_fatal = 99
            return qr

        pipe = _make_pipeline()
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=0,
            retry_on=("fatal",),
        )

        assert gen_calls == 1

    async def test_no_retry_when_condition_not_in_retry_on(self):
        """质检失败但条件未在 retry_on 中时不重试"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result()

        async def qual(_):
            qr = QualityReport()
            qr.consistency_fatal = 1  # 失败
            return qr

        pipe = _make_pipeline()
        # retry_on 只监听 reader — 即使有 fatal 也不重试
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=3,
            retry_on=("reader",),
        )

        assert gen_calls == 1
        assert qr.consistency_fatal == 1

    async def test_multiple_conditions_triggered(self):
        """多个条件同时触发也会重试"""
        gen_calls = 0

        async def gen():
            nonlocal gen_calls
            gen_calls += 1
            return _result()

        qual_calls = 0

        async def qual(_):
            nonlocal qual_calls
            qual_calls += 1
            qr = QualityReport()
            if qual_calls < 2:
                qr.consistency_fatal = 1
                qr.reader_want_next = False
                qr.tension_score = 2
                qr.reader_repetitive = True
            return qr

        pipe = _make_pipeline()
        _, qr = await pipe.run_with_retry(
            generate_fn=gen, quality_fn=qual, max_retries=3,
            retry_on=("fatal", "reader", "tension_low", "repetitive"),
        )

        assert gen_calls == 2
        assert qr.consistency_fatal == 0
