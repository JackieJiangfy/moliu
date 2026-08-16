"""编排层单元测试 — 全部离线"""

from pathlib import Path

import pytest

from moliu.orchestrator.pipeline import QualityReport


class TestQualityReport:
    def test_default_can_advance(self):
        qr = QualityReport()
        assert qr.can_advance() is True

    def test_fatal_blocks_advance(self):
        qr = QualityReport()
        qr.consistency_fatal = 1
        assert qr.can_advance() is False

    def test_warnings_dont_block(self):
        qr = QualityReport()
        qr.consistency_warn = 5
        assert qr.can_advance() is True

    def test_summary_clean(self):
        qr = QualityReport()
        qr.pre_check_passed = True
        s = qr.summary()
        assert "锚点预检通过" in s
        assert "一致性检查通过" in s

    def test_summary_with_issues(self):
        qr = QualityReport()
        qr.consistency_fatal = 1
        qr.consistency_warn = 2
        qr.reader_want_next = False
        qr.reader_repetitive = True
        qr.tension_score = 3
        s = qr.summary()
        assert "致命" in s
        assert "不想继续" in s
        assert "重复" in s
        assert "3/10" in s


# === 问题9: checker/reader 并发隔离 ===

class TestConcurrentQualityChecks:
    """问题9: checker 和 reader 并发执行测试"""

    @pytest.mark.asyncio
    async def test_checker_and_reader_run_concurrently(self, tmp_path):
        """checker 和 reader 应并发执行,总耗时约等于较慢者而非两者之和"""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from moliu.config import Config
        from moliu.orchestrator.pipeline import ChapterPipeline
        from moliu.data.schemas import ChapterResult

        config = Config()
        config.project_dir = tmp_path
        config.data_dir = "data"
        config.output_dir = "output/chapters"

        pipeline = ChapterPipeline.__new__(ChapterPipeline)

        # checker 和 reader 各 sleep 0.1s
        async def slow_check(*args, **kwargs):
            await asyncio.sleep(0.1)
            mock_report = MagicMock()
            mock_report.to_text.return_value = "一致性通过"
            mock_report.fatal_count = 0
            mock_report.warning_count = 1
            return mock_report

        async def slow_eval(*args, **kwargs):
            await asyncio.sleep(0.1)
            fb = MagicMock()
            fb.summary.return_value = "读者想继续"
            fb.want_next = True
            fb.feels_repetitive = False
            return fb

        pipeline.checker = MagicMock()
        pipeline.checker.check = slow_check
        pipeline.reader = MagicMock()
        pipeline.reader.evaluate = slow_eval

        result = ChapterResult(chapter_num=1, content="测试内容", word_count=4, model_used="test", tokens_used=10)

        import time
        start = time.monotonic()
        qr = await pipeline.run_quality_checks(
            result, beat="节拍", characters=[], world=None,
        )
        elapsed = time.monotonic() - start

        # 并发:总耗时应 < 两者之和(0.2s),约等于单个(0.1s)+ 些许开销
        assert elapsed < 0.18, f"并发执行失败,耗时 {elapsed:.3f}s"
        assert qr.consistency_fatal == 0
        assert qr.reader_want_next is True

    @pytest.mark.asyncio
    async def test_checker_failure_doesnt_block_reader(self, tmp_path):
        """问题9: checker 失败时 reader 仍应正常完成"""
        from unittest.mock import AsyncMock, MagicMock
        from moliu.config import Config
        from moliu.orchestrator.pipeline import ChapterPipeline
        from moliu.data.schemas import ChapterResult

        config = Config()
        config.project_dir = tmp_path

        pipeline = ChapterPipeline.__new__(ChapterPipeline)

        pipeline.checker = MagicMock()
        pipeline.checker.check = AsyncMock(side_effect=RuntimeError("checker 挂了"))

        pipeline.reader = MagicMock()
        fb = MagicMock()
        fb.summary.return_value = "读者反馈"
        fb.want_next = True
        fb.feels_repetitive = False
        pipeline.reader.evaluate = AsyncMock(return_value=fb)

        result = ChapterResult(chapter_num=1, content="内容", word_count=2, model_used="test", tokens_used=5)
        qr = await pipeline.run_quality_checks(
            result, beat="节拍", characters=[], world=None,
        )

        # checker 失败:consistency 保持默认(空)
        assert qr.consistency_fatal == 0
        # reader 正常完成
        assert qr.reader_want_next is True
        assert "读者反馈" in qr.reader_feedback

    @pytest.mark.asyncio
    async def test_reader_failure_doesnt_block_checker(self, tmp_path):
        """问题9: reader 失败时 checker 仍应正常完成"""
        from unittest.mock import AsyncMock, MagicMock
        from moliu.config import Config
        from moliu.orchestrator.pipeline import ChapterPipeline
        from moliu.data.schemas import ChapterResult

        config = Config()
        config.project_dir = tmp_path

        pipeline = ChapterPipeline.__new__(ChapterPipeline)

        pipeline.checker = MagicMock()
        report = MagicMock()
        report.to_text.return_value = "一致性通过"
        report.fatal_count = 0
        report.warning_count = 2
        pipeline.checker.check = AsyncMock(return_value=report)

        pipeline.reader = MagicMock()
        pipeline.reader.evaluate = AsyncMock(side_effect=RuntimeError("reader 挂了"))

        result = ChapterResult(chapter_num=1, content="内容", word_count=2, model_used="test", tokens_used=5)
        qr = await pipeline.run_quality_checks(
            result, beat="节拍", characters=[], world=None,
        )

        # checker 正常完成
        assert qr.consistency_fatal == 0
        assert qr.consistency_warn == 2
        # reader 失败:reader 字段保持默认
        assert qr.reader_want_next is True  # 默认值
        assert qr.reader_feedback == ""

    @pytest.mark.asyncio
    async def test_no_checker_no_reader_only_tension(self, tmp_path):
        """问题9: 无 checker 和 reader 时只计算张力评分"""
        from moliu.config import Config
        from moliu.orchestrator.pipeline import ChapterPipeline
        from moliu.data.schemas import ChapterResult

        config = Config()
        config.project_dir = tmp_path

        pipeline = ChapterPipeline.__new__(ChapterPipeline)
        pipeline.checker = None
        pipeline.reader = None

        result = ChapterResult(chapter_num=1, content="紧张的内容", word_count=5, model_used="test", tokens_used=10)
        qr = await pipeline.run_quality_checks(
            result, beat="节拍", characters=[], world=None,
        )

        # 只计算了张力
        assert qr.tension_score > 0
        assert qr.consistency == ""
        assert qr.reader_feedback == ""
