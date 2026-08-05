"""节奏追踪器单元测试 — 全部离线"""

from pathlib import Path

import pytest

from moliu.rules.rhythm_tracker import RhythmRecord, RhythmTracker, TensionScorer


class TestTensionScorer:
    def test_high_tension(self):
        score = TensionScorer.score("突然一声枪响！他猛地冲了出去，血溅了一地。危机来了！")
        assert score >= 7, f"Expected >=7, got {score}"

    def test_low_tension(self):
        score = TensionScorer.score("她安静地坐在窗边，阳光洒在茶杯里，温馨的午后。")
        assert score <= 5, f"Expected <=5, got {score}"

    def test_neutral(self):
        score = TensionScorer.score("他走在路上，看了看四周。")
        assert 3 <= score <= 7

    def test_detect_opening_dialogue(self):
        assert TensionScorer.detect_opening('"你怎么来了？"他问。') == "对话开场"

    def test_detect_opening_action(self):
        assert TensionScorer.detect_opening("他突然推开门冲了进来——") == "动作开场"

    def test_detect_opening_inner(self):
        assert TensionScorer.detect_opening("他想起了昨天的事，心里有些不安。") == "内心独白"

    def test_detect_opening_scene(self):
        assert TensionScorer.detect_opening("清晨的阳光透过窗帘洒进来。") == "场景开场"

    def test_detect_closing_suspense(self):
        assert TensionScorer.detect_closing("她看着窗外，天已经黑了……") == "悬念钩子"

    def test_detect_closing_emotion(self):
        assert TensionScorer.detect_closing("一切终于安静下来，她露出了微笑。") == "情绪收束"

    def test_detect_closing_dialogue(self):
        assert TensionScorer.detect_closing('"那明天见。"他说。') == "对话收尾"


class TestRhythmTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        return RhythmTracker(tmp_path)

    def test_record_and_load(self, tracker):
        tracker.record(RhythmRecord(chapter_num=1, chapter_type="opening", tension_score=7))
        records = tracker.load_all()
        assert len(records) == 1
        assert records[0].tension_score == 7

    def test_multiple_records(self, tracker):
        for i in range(5):
            tracker.record(RhythmRecord(chapter_num=i + 1, tension_score=5))
        assert len(tracker.load_all()) == 5

    def test_check_variety_same_opening(self, tracker):
        for i in range(3):
            tracker.record(RhythmRecord(
                chapter_num=i + 1, opening_style="场景开场",
                tension_score=5, has_memorable_moment=True,
            ))
        alerts = tracker.check_variety(3)
        assert any("开场" in a for a in alerts)

    def test_check_variety_no_memory(self, tracker):
        for i in range(3):
            tracker.record(RhythmRecord(
                chapter_num=i + 1, opening_style="对话开场" if i == 0 else "动作开场",
                tension_score=5, has_memorable_moment=False,
            ))
        alerts = tracker.check_variety(3)
        assert any("记忆点" in a for a in alerts)

    def test_check_variety_few_chapters(self, tracker):
        tracker.record(RhythmRecord(chapter_num=1))
        assert tracker.check_variety() == []

    def test_tension_curve(self, tracker):
        scores = [5, 6, 7, 8, 4]
        for i, s in enumerate(scores):
            tracker.record(RhythmRecord(chapter_num=i + 1, tension_score=s))
        assert tracker.tension_curve() == scores
