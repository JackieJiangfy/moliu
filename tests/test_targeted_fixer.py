"""定向修复器 (P1-2) 测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from moliu.config import Config
from moliu.data.schemas import ChapterResult
from moliu.engines.targeted_fixer import FixResult, TargetedFixer
from moliu.orchestrator.pipeline import ChapterPipeline, QualityReport


@pytest.fixture
def tmp_config(tmp_path):
    config = Config()
    config.project_dir = tmp_path
    config.data_dir = "data"
    config.output_dir = "output/chapters"
    return config


@pytest.fixture
def fixer(tmp_config):
    return TargetedFixer(tmp_config)


@pytest.fixture
def good_qr():
    """无问题的质检报告"""
    qr = QualityReport()
    qr.consistency_fatal = 0
    qr.consistency_warn = 0
    qr.tension_score = 7
    qr.reader_want_next = True
    qr.reader_repetitive = False
    qr.rhythm_alerts = []
    return qr


@pytest.fixture
def bad_qr():
    """有问题的质检报告"""
    qr = QualityReport()
    qr.consistency_fatal = 2
    qr.consistency_warn = 1
    qr.consistency = "致命: 角色名字前后不一致\n致命: 时间线矛盾\n警告: 描写重复"
    qr.tension_score = 3
    qr.reader_want_next = False
    qr.reader_repetitive = True
    qr.rhythm_alerts = ["连续 3 章对话过多"]
    return qr


# === 问题收集 ===

class TestCollectIssues:
    def test_no_issues_when_good(self, fixer, good_qr):
        """质检通过时无问题"""
        issues = fixer._collect_issues(good_qr)
        assert len(issues) == 0

    def test_collects_fatal_issues(self, fixer, bad_qr):
        """收集致命问题"""
        issues = fixer._collect_issues(bad_qr)
        # 应至少包含致命问题、读者反馈、张力、节奏
        assert len(issues) >= 4
        # 致命问题包含详情
        fatal_issue = [i for i in issues if "致命" in i]
        assert len(fatal_issue) == 1
        assert "2 个致命" in fatal_issue[0]

    def test_collects_tension_low(self, fixer):
        """张力低被收集"""
        qr = QualityReport()
        qr.tension_score = 2
        issues = fixer._collect_issues(qr)
        tension_issue = [i for i in issues if "张力" in i]
        assert len(tension_issue) == 1

    def test_collects_reader_not_want_next(self, fixer):
        """读者不想继续被收集"""
        qr = QualityReport()
        qr.reader_want_next = False
        issues = fixer._collect_issues(qr)
        assert any("不想继续" in i for i in issues)

    def test_collects_repetitive(self, fixer):
        """读者感觉重复被收集"""
        qr = QualityReport()
        qr.reader_repetitive = True
        issues = fixer._collect_issues(qr)
        assert any("重复" in i for i in issues)

    def test_collects_rhythm_alerts(self, fixer):
        """节奏告警被收集"""
        qr = QualityReport()
        qr.rhythm_alerts = ["连续 5 章开头雷同", "对话比例过高"]
        issues = fixer._collect_issues(qr)
        rhythm_issues = [i for i in issues if "节奏" in i]
        assert len(rhythm_issues) == 2


# === 修复流程 ===

class TestFix:
    @pytest.mark.asyncio
    async def test_no_gateway_returns_failure(self, fixer, bad_qr):
        """无 gateway 时返回失败"""
        result = await fixer.fix(
            original_content="内容",
            quality_report=bad_qr,
            chapter_num=1,
        )
        assert not result.success
        assert "无 LLM" in result.fix_log[0]

    @pytest.mark.asyncio
    async def test_no_issues_returns_success(self, fixer, good_qr):
        """无问题时直接返回成功"""
        mock_gateway = MagicMock()
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="内容",
            quality_report=good_qr,
            chapter_num=1,
        )
        assert result.success
        assert result.final_content == "内容"
        assert result.iterations == 0
        # 不应调用 LLM
        mock_gateway.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix_calls_llm_with_issues(self, fixer, bad_qr):
        """修复时调用 LLM 并传递问题"""
        fixed_content = "这是修复后的内容,增加了更多冲突和细节描写。" * 10
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(fixed_content, 500))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始内容" * 50,
            quality_report=bad_qr,
            chapter_num=5,
            beat="主角觉醒能力",
        )
        assert result.success
        assert result.final_content == fixed_content
        assert result.tokens_used == 500
        assert result.iterations == 1

        # 验证 LLM 调用参数
        call_args = mock_gateway.generate.call_args
        user_prompt = call_args.kwargs.get("user_prompt", "")
        assert "原始内容" in user_prompt
        assert "主角觉醒能力" in user_prompt  # beat
        assert "致命" in user_prompt  # 问题清单

    @pytest.mark.asyncio
    async def test_short_response_fails(self, fixer, bad_qr):
        """LLM 返回过短内容视为失败"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("短", 10))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始内容" * 50,
            quality_report=bad_qr,
            chapter_num=1,
        )
        assert not result.success
        # 日志中应包含过短提示
        assert any("过短" in msg for msg in result.fix_log)
        # 保留原始内容
        assert result.final_content == "原始内容" * 50

    @pytest.mark.asyncio
    async def test_llm_failure_keeps_original(self, fixer, bad_qr):
        """LLM 调用失败时保留原始内容"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(side_effect=Exception("API 错误"))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始内容",
            quality_report=bad_qr,
            chapter_num=1,
        )
        assert not result.success
        assert result.final_content == "原始内容"

    @pytest.mark.asyncio
    async def test_strips_chapter_title(self, fixer, bad_qr):
        """去掉 LLM 输出中的章节标题"""
        fixed = "第5章 觉醒\n\n这是修复后的内容,增加了更多冲突和细节描写。" * 10
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(fixed, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 50,
            quality_report=bad_qr,
            chapter_num=5,
        )
        assert not result.final_content.startswith("第5章")

    @pytest.mark.asyncio
    async def test_strips_markdown_wrapper(self, fixer, bad_qr):
        """去掉 markdown 代码块包裹"""
        fixed = "```\n这是修复后的内容,增加了更多冲突和细节描写。" * 10 + "\n```"
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(fixed, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 50,
            quality_report=bad_qr,
            chapter_num=5,
        )
        assert not result.final_content.startswith("```")


# === 问题8: 多轮迭代 ===

class TestMultiIteration:
    """问题8: 定向修复支持多轮迭代(传入 quality_check_fn)"""

    @pytest.mark.asyncio
    async def test_passes_on_first_iteration(self, fixer, bad_qr, good_qr):
        """第 1 轮修复后质检通过,应停止迭代"""
        call_count = {"qc": 0}

        async def fake_qc(content: str):
            call_count["qc"] += 1
            return good_qr

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后的内容" * 30, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始内容" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=3,
            quality_check_fn=fake_qc,
        )
        assert result.success
        assert result.iterations == 1
        assert mock_gateway.generate.call_count == 1
        assert call_count["qc"] == 1
        assert result.final_qr is good_qr

    @pytest.mark.asyncio
    async def test_iterates_until_pass(self, fixer, bad_qr):
        """第 1 轮未通过、第 2 轮通过,应迭代 2 轮"""
        call_count = {"llm": 0, "qc": 0}
        good_qr = QualityReport()
        good_qr.consistency_fatal = 0
        good_qr.tension_score = 7
        good_qr.reader_want_next = True
        good_qr.reader_repetitive = False
        good_qr.rhythm_alerts = []

        async def fake_qc(content: str):
            call_count["qc"] += 1
            # 第 1 次质检:仍有问题;第 2 次:通过
            if call_count["qc"] == 1:
                return bad_qr
            return good_qr

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复内容" * 30, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=3,
            quality_check_fn=fake_qc,
        )
        assert result.success
        assert result.iterations == 2
        assert call_count["qc"] == 2
        # issues_history 应记录:初始 + 第1轮后 + 第2轮后 = 3 条
        assert len(result.issues_history) == 3

    @pytest.mark.asyncio
    async def test_max_iterations_exhausted(self, fixer, bad_qr):
        """达到 max_iterations 仍未通过,应返回 success=False 并保留最后内容"""
        call_count = {"llm": 0, "qc": 0}

        async def fake_qc(content: str):
            call_count["qc"] += 1
            return bad_qr  # 永远不通过

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后的内容" * 30, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=2,
            quality_check_fn=fake_qc,
        )
        assert not result.success
        assert result.iterations == 2
        assert call_count["qc"] == 2
        # 保留最后一次修复的内容(不是原始内容)
        assert "修复后的内容" in result.final_content
        assert result.final_qr is bad_qr

    @pytest.mark.asyncio
    async def test_no_quality_fn_single_iteration(self, fixer, bad_qr):
        """不传 quality_check_fn 时,单次修复即返回(向后兼容)"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后的内容" * 30, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=3,
            # 不传 quality_check_fn
        )
        assert result.success
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_quality_fn_exception_breaks_loop(self, fixer, bad_qr):
        """质检回调抛异常时,应中止迭代并保留已修复内容"""
        async def fake_qc(content: str):
            raise RuntimeError("质检服务挂了")

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后的内容" * 30, 200))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=3,
            quality_check_fn=fake_qc,
        )
        assert not result.success
        assert result.iterations == 1
        # 保留已修复内容
        assert "修复后的内容" in result.final_content
        # 日志应记录质检失败
        assert any("重新质检失败" in log for log in result.fix_log)

    @pytest.mark.asyncio
    async def test_issues_history_grows_with_iterations(self, fixer, bad_qr):
        """issues_history 应随迭代轮次增长"""
        good_qr = QualityReport()
        good_qr.consistency_fatal = 0
        good_qr.tension_score = 8
        good_qr.reader_want_next = True
        good_qr.reader_repetitive = False
        good_qr.rhythm_alerts = []

        qc_calls = {"n": 0}

        async def fake_qc(content: str):
            qc_calls["n"] += 1
            # 第 1 次不通过(改用 warn 级别),第 2 次通过
            if qc_calls["n"] == 1:
                mid_qr = QualityReport()
                mid_qr.consistency_fatal = 0
                mid_qr.consistency_warn = 2
                mid_qr.tension_score = 6
                mid_qr.reader_want_next = True
                mid_qr.reader_repetitive = False
                mid_qr.rhythm_alerts = []
                return mid_qr
            return good_qr

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后的内容" * 30, 100))
        fixer.gateway = mock_gateway

        result = await fixer.fix(
            original_content="原始" * 30,
            quality_report=bad_qr,
            chapter_num=5,
            max_iterations=3,
            quality_check_fn=fake_qc,
        )
        # 初始问题 + 第 1 轮后问题(空) = 2 条
        assert len(result.issues_history) == 2
        # 第 1 轮后的问题数应 < 初始(因 warn 级别不会被 _collect_issues 收集)
        assert len(result.issues_history[0]) > 0
        assert len(result.issues_history[1]) == 0


# === Pipeline 集成 ===

class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_run_with_retry_uses_targeted_fix(self, tmp_config):
        """run_with_retry 优先使用定向修复"""
        # 构造 pipeline
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("修复后内容" * 50, 300))
        pipeline = ChapterPipeline(
            tmp_config, mock_gateway, prompts=MagicMock(),
        )

        # 第一次质检 fatal=1,第二次质检 fatal=0
        call_count = [0]
        async def quality_fn(result):
            call_count[0] += 1
            qr = QualityReport()
            if call_count[0] == 1:
                qr.consistency_fatal = 1
                qr.consistency = "致命: 名字不一致"
            else:
                qr.consistency_fatal = 0
            return qr

        async def generate_fn():
            return ChapterResult(
                chapter_num=1, content="原始" * 50, word_count=100,
                model_used="deepseek-chat", tokens_used=1000,
            )

        result, qr = await pipeline.run_with_retry(
            generate_fn=generate_fn,
            quality_fn=quality_fn,
            max_retries=1,
            retry_on=("fatal",),
            chapter_num=1,
            beat="test",
            use_targeted_fix=True,
        )
        # 应调用过 LLM 修复
        assert mock_gateway.generate.called
        # 最终 fatal 应为 0
        assert qr.consistency_fatal == 0

    @pytest.mark.asyncio
    async def test_run_with_retry_falls_back_to_regenerate(self, tmp_config):
        """定向修复失败时降级到无脑重试"""
        # gateway 修复返回过短内容
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("短", 10))
        pipeline = ChapterPipeline(
            tmp_config, mock_gateway, prompts=MagicMock(),
        )

        call_count = [0]
        async def quality_fn(result):
            call_count[0] += 1
            qr = QualityReport()
            qr.consistency_fatal = 1  # 始终 fatal
            qr.consistency = "致命: 问题"
            return qr

        gen_count = [0]
        async def generate_fn():
            gen_count[0] += 1
            return ChapterResult(
                chapter_num=1, content=f"生成内容{gen_count[0]}" * 50, word_count=100,
                model_used="deepseek-chat", tokens_used=1000,
            )

        result, qr = await pipeline.run_with_retry(
            generate_fn=generate_fn,
            quality_fn=quality_fn,
            max_retries=1,
            retry_on=("fatal",),
            chapter_num=1,
            use_targeted_fix=True,
        )
        # 应调用了 2 次 generate(原始 + 1 次重试)
        assert gen_count[0] == 2

    @pytest.mark.asyncio
    async def test_run_with_retry_no_retry_when_passed(self, tmp_config):
        """质检通过时不重试"""
        mock_gateway = MagicMock()
        pipeline = ChapterPipeline(
            tmp_config, mock_gateway, prompts=MagicMock(),
        )

        async def quality_fn(result):
            qr = QualityReport()
            qr.consistency_fatal = 0
            return qr

        gen_count = [0]
        async def generate_fn():
            gen_count[0] += 1
            return ChapterResult(
                chapter_num=1, content="内容" * 50, word_count=100,
                model_used="deepseek-chat", tokens_used=1000,
            )

        await pipeline.run_with_retry(
            generate_fn=generate_fn,
            quality_fn=quality_fn,
            max_retries=2,
            chapter_num=1,
        )
        assert gen_count[0] == 1
        # 不应调用 LLM
        mock_gateway.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_retry_disabled_targeted_fix(self, tmp_config):
        """use_targeted_fix=False 时走无脑重试"""
        mock_gateway = MagicMock()
        pipeline = ChapterPipeline(
            tmp_config, mock_gateway, prompts=MagicMock(),
        )

        async def quality_fn(result):
            qr = QualityReport()
            qr.consistency_fatal = 1
            qr.consistency = "致命"
            return qr

        gen_count = [0]
        async def generate_fn():
            gen_count[0] += 1
            return ChapterResult(
                chapter_num=1, content="内容" * 50, word_count=100,
                model_used="deepseek-chat", tokens_used=1000,
            )

        await pipeline.run_with_retry(
            generate_fn=generate_fn,
            quality_fn=quality_fn,
            max_retries=1,
            retry_on=("fatal",),
            chapter_num=1,
            use_targeted_fix=False,
        )
        # 应调用 2 次 generate
        assert gen_count[0] == 2
        # 不应调用 LLM 修复
        mock_gateway.generate.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
