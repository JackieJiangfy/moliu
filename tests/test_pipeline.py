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
