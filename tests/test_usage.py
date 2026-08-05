"""用量追踪器单元测试 — 全部离线"""

import json
from pathlib import Path

import pytest

from moliu.engines.usage import UsageTracker


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "usage_log.jsonl"


@pytest.fixture
def tracker(log_path):
    return UsageTracker(log_path, monthly_budget=100000)


class TestUsageTracker:
    def test_log_and_today(self, tracker, log_path):
        tracker.log("write", "deepseek-chat", 5000, chapter_num=1)
        assert tracker.today() >= 5000

    def test_empty_tracker(self, tracker):
        assert tracker.today() == 0
        assert tracker.average_per_chapter() == 0.0

    def test_by_chapter(self, tracker):
        tracker.log("write", "deepseek-chat", 4000, chapter_num=1)
        tracker.log("check", "deepseek-chat", 2000, chapter_num=1)
        tracker.log("write", "deepseek-chat", 6000, chapter_num=2)
        by_ch = tracker.by_chapter()
        assert by_ch[1] == 6000
        assert 2 in by_ch

    def test_by_command(self, tracker):
        tracker.log("write", "m", 3000)
        tracker.log("write", "m", 5000)
        tracker.log("check", "m", 1000)
        by_cmd = tracker.by_command()
        assert by_cmd["write"] == 8000
        assert by_cmd["check"] == 1000

    def test_average_per_chapter(self, tracker):
        tracker.log("write", "m", 4000, chapter_num=1)
        tracker.log("write", "m", 6000, chapter_num=2)
        assert tracker.average_per_chapter() == 5000.0

    def test_budget_status(self, tracker):
        tracker.log("write", "m", 30000)
        status = tracker.budget_status()
        assert "30000" in status or "30,000" in status
        assert "100,000" in status or "100000" in status

    def test_budget_unset(self, log_path):
        t = UsageTracker(log_path, monthly_budget=0)
        assert "未设置" in t.budget_status()

    def test_prompt_completion_tokens_saved(self, tracker, log_path):
        tracker.log("write", "m", 5000, prompt_tokens=3000, completion_tokens=2000)
        line = log_path.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["prompt_tokens"] == 3000
        assert record["completion_tokens"] == 2000
