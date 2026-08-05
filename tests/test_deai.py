"""去AI味检测器单元测试 — 全部离线"""

from moliu.deai.detector import DeAIDetector, L1_PATTERNS


class TestDeAIDetector:
    def setup_method(self):
        self.d = DeAIDetector()

    def test_detect_emotion_cliche(self):
        r = self.d.detect_l1("他心中涌起一股暖流，不由得笑了。")
        assert "情绪内化套话" in r.tic_counts
        assert "机械反应描写" in r.tic_counts

    def test_detect_eye_cliche(self):
        r = self.d.detect_l1("她眼中闪过一丝惊讶，仿佛看到了什么不可思议的东西一般。")
        assert "眼神过度解读" in r.tic_counts
        assert "比喻堆叠" in r.tic_counts

    def test_clean_text_scores_high(self):
        r = self.d.detect_l1("他放下杯子。转身。门在身后关上。")
        assert r.overall_score > 0.8

    def test_heavily_ai_text_scores_low(self):
        text = ("他心中涌起一阵暖流，不由得感慨万千。"
                "她眼中闪过一丝光芒，仿佛看到了希望一般。"
                "他不由得想到，这或许就是命运的安排。"
                "她内心深处知道，这一切才刚刚开始。")
        r = self.d.detect_l1(text)
        assert r.overall_score < 0.9

    def test_hard_violation_triggers(self):
        text = "心中涌起一阵暖流。心中升起一股感动。心中泛起涟漪。"
        r = self.d.detect_l1(text)
        assert "情绪内化套话" in r.hard_violations or any("情绪内化套话" in v for v in r.hard_violations)

    def test_l2_candidates_show_then_tell(self):
        text = "他转身走了。他知道自己不会再回来了，这意味着一切都结束了。"
        candidates = self.d.detect_l2_candidates(text)
        assert len(candidates) >= 1

    def test_l2_candidates_emotional_softening(self):
        text = "她有些生气地说：你为什么不告诉我。"
        candidates = self.d.detect_l2_candidates(text)
        assert len(candidates) >= 1

    def test_l2_candidates_filter_words(self):
        text = "他看到窗外的雨停了。她听到门铃响了。"
        candidates = self.d.detect_l2_candidates(text)
        assert len(candidates) >= 1

    def test_patterns_count(self):
        assert len(L1_PATTERNS) == 24

    def test_empty_content(self):
        r = self.d.detect_l1("")
        assert r.overall_score == 1.0
        assert len(r.hard_violations) == 0
