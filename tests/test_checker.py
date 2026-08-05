"""一致性检查器单元测试 — 全部离线"""

import pytest
from moliu.engines.checker import CheckIssue, CheckReport, ConsistencyChecker


class TestCheckReport:
    def test_empty_report_passed(self):
        r = CheckReport()
        assert r.passed is True
        assert r.fatal_count == 0
        assert r.warning_count == 0

    def test_fatal_makes_passed_false(self):
        r = CheckReport()
        r.issues.append(CheckIssue(severity="fatal", category="character_voice", description="角色崩了", evidence="原文"))
        r.fatal_count = 1
        r.passed = False
        assert not r.passed
        assert r.fatal_count == 1

    def test_warning_keeps_passed_true(self):
        r = CheckReport()
        r.issues.append(CheckIssue(severity="warning", category="world_rules", description="轻微设定问题", evidence=""))
        r.warning_count = 1
        assert r.passed is True

    def test_to_text(self):
        r = CheckReport()
        r.issues.append(CheckIssue(severity="fatal", category="character_voice", description="林默说了禁用词", evidence="太好了！", suggestion="改为\"行。\""))
        r.fatal_count = 1
        r.passed = False
        text = r.to_text()
        assert "[FAIL]" in text
        assert "禁用词" in text
        assert "太好了" in text

    def test_to_text_empty(self):
        r = CheckReport()
        assert "全部通过" in r.to_text()


class TestParseReport:
    def test_parse_pass(self):
        c = ConsistencyChecker(None)
        r = c._parse_report("PASS: 未发现一致性问题。")
        assert r.passed is True
        assert r.fatal_count == 0

    def test_parse_fatal(self):
        c = ConsistencyChecker(None)
        r = c._parse_report("fatal: [character_voice] 角色说话风格严重偏离")
        assert r.fatal_count >= 1
        assert not r.passed

    def test_parse_warning(self):
        c = ConsistencyChecker(None)
        r = c._parse_report("warning: [narrative_quality] 套话出现")
        assert r.warning_count >= 1
        assert r.passed is True

    def test_parse_multiple_issues(self):
        c = ConsistencyChecker(None)
        text = """fatal: 世界观规则违反
warning: 角色对话单调
info: 建议加强收尾钩子"""
        r = c._parse_report(text)
        assert r.fatal_count >= 1
        assert r.warning_count >= 1

    def test_parse_categories(self):
        c = ConsistencyChecker(None)
        r = c._parse_report("fatal: 角色说话风格完全错误")
        chars = [i.category for i in r.issues if i.category == "character_voice"]
        assert len(chars) >= 1

        r2 = c._parse_report("warning: 世界规则冲突")
        worlds = [i.category for i in r2.issues if i.category == "world_rules"]
        assert len(worlds) >= 1

        r3 = c._parse_report("warning: 剧情逻辑因果不通")
        plots = [i.category for i in r3.issues if i.category == "plot_logic"]
        assert len(plots) >= 1
