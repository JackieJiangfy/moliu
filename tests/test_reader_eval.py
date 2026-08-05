"""读者评估器单元测试 — 全部离线"""

import pytest
from moliu.engines.reader_eval import ReaderEvaluator, ReaderFeedback


class TestReaderFeedback:
    def test_defaults(self):
        fb = ReaderFeedback()
        assert fb.want_next is True
        assert fb.feels_repetitive is False
        assert fb.skip_paragraphs == []
        assert fb.memorable == ""

    def test_summary_want_next(self):
        fb = ReaderFeedback(want_next=True, feels_repetitive=False, emotional_moment="看到林默笑的时候")
        s = fb.summary()
        assert "想继续" in s

    def test_summary_dont_want(self):
        fb = ReaderFeedback(want_next=False, feels_repetitive=True)
        s = fb.summary()
        assert "不想继续" in s
        assert "重复" in s

    def test_skip_paragraphs_defaults_to_empty_list(self):
        fb = ReaderFeedback()
        assert isinstance(fb.skip_paragraphs, list)
        assert len(fb.skip_paragraphs) == 0


class TestParse:
    def test_parse_wants_next(self):
        e = ReaderEvaluator(None)
        fb = e._parse("想立刻看下一章！这章太好了")
        assert fb.want_next is True

    def test_parse_not_want(self):
        e = ReaderEvaluator(None)
        fb = e._parse("不太想看下一章，这章有点无聊")
        assert fb.want_next is False

    def test_parse_feels_repetitive_true(self):
        e = ReaderEvaluator(None)
        fb = e._parse("感觉和上一章有点重复，节奏雷同")
        assert fb.feels_repetitive is True

    def test_parse_feels_repetitive_false(self):
        e = ReaderEvaluator(None)
        fb = e._parse("这章和上一章不太一样，没有重复的感觉")
        assert fb.feels_repetitive is False

    def test_parse_no_repetition(self):
        e = ReaderEvaluator(None)
        fb = e._parse("没有重复，这章很新鲜")
        assert fb.feels_repetitive is False

    def test_parse_empty_feedback(self):
        e = ReaderEvaluator(None)
        fb = e._parse("")
        assert fb.want_next is True
        assert fb.feels_repetitive is False
