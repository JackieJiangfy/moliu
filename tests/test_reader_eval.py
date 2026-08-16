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

    # === 问题6: JSON 格式解析 ===

    def test_parse_json_full(self):
        """问题6: 完整 JSON 输出正确解析"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "skip_paragraphs": ["第二段对话太长", "第四段描写拖沓"],
            "memorable": "主角在悬崖边的选择",
            "emotional_moment": "主角决定跳崖时的紧张感",
            "want_next": True,
            "feels_repetitive": False,
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert fb.want_next is True
        assert fb.feels_repetitive is False
        assert len(fb.skip_paragraphs) == 2
        assert "悬崖" in fb.memorable
        assert "紧张" in fb.emotional_moment

    def test_parse_json_want_next_false(self):
        """问题6: want_next=false 正确解析"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "skip_paragraphs": [],
            "memorable": "没记住什么",
            "emotional_moment": "无",
            "want_next": False,
            "feels_repetitive": True,
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert fb.want_next is False
        assert fb.feels_repetitive is True
        assert fb.skip_paragraphs == []

    def test_parse_json_with_markdown_wrapper(self):
        """问题6: JSON 被 markdown 包裹时也能解析"""
        import json
        e = ReaderEvaluator(None)
        inner = json.dumps({
            "skip_paragraphs": ["对话段落"],
            "memorable": "主角的独白",
            "emotional_moment": "结尾的反转",
            "want_next": True,
            "feels_repetitive": False,
        }, ensure_ascii=False)
        text = f"```json\n{inner}\n```"
        fb = e._parse(text)
        assert fb.want_next is True
        assert "独白" in fb.memorable
        assert "反转" in fb.emotional_moment

    def test_parse_json_string_bool_fields(self):
        """问题6: bool 字段用字符串"true"/"false"时也能解析"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "skip_paragraphs": [],
            "memorable": "测试",
            "emotional_moment": "无",
            "want_next": "false",
            "feels_repetitive": "true",
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert fb.want_next is False
        assert fb.feels_repetitive is True

    def test_parse_json_partial_fields(self):
        """问题6: JSON 缺少部分字段时使用默认值"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "memorable": "只有记忆点",
            # 缺少其他字段
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert fb.memorable == "只有记忆点"
        assert fb.want_next is True  # 默认
        assert fb.feels_repetitive is False  # 默认
        assert fb.skip_paragraphs == []

    def test_parse_json_skip_paragraphs_as_string(self):
        """问题6: skip_paragraphs 为字符串时转为单元素列表"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "skip_paragraphs": "只有一段想跳过",
            "memorable": "",
            "emotional_moment": "",
            "want_next": True,
            "feels_repetitive": False,
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert len(fb.skip_paragraphs) == 1
        assert "只有一段" in fb.skip_paragraphs[0]

    def test_parse_invalid_json_falls_back_to_legacy(self):
        """问题6: 无效 JSON 时回退到关键词解析"""
        e = ReaderEvaluator(None)
        # 故意构造非 JSON 文本,触发回退
        text = "这章不太想看下一章,感觉有重复,记住了主角的独白"
        fb = e._parse(text)
        # legacy 解析能识别"不太想"
        assert fb.want_next is False
        assert fb.feels_repetitive is True

    def test_parse_json_raw_feedback_preserved(self):
        """问题6: JSON 解析成功时 raw_feedback 保留原文"""
        import json
        e = ReaderEvaluator(None)
        text = json.dumps({
            "skip_paragraphs": [],
            "memorable": "测试",
            "emotional_moment": "无",
            "want_next": True,
            "feels_repetitive": False,
        }, ensure_ascii=False)
        fb = e._parse(text)
        assert fb.raw_feedback == text
