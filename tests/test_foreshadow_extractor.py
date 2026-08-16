"""伏笔自动提取器 (P1-1) 测试"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from moliu.config import Config
from moliu.data.schemas import ChapterPlan
from moliu.engines.foreshadow_extractor import (
    ExtractedForeshadow,
    ExtractResult,
    ForeshadowExtractor,
    extract_and_apply_foreshadows,
)
from moliu.rules.foreshadow_watch import ForeshadowManager


@pytest.fixture
def tmp_config(tmp_path):
    config = Config()
    config.project_dir = tmp_path
    config.data_dir = Path("data")
    config.output_dir = Path("output/chapters")
    (tmp_path / "data" / "novels" / "1").mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def extractor(tmp_config):
    return ForeshadowExtractor(tmp_config, novel_id=1)


@pytest.fixture
def manager(tmp_config):
    return ForeshadowManager(tmp_config.resolve_data_dir(1))


# === 测试样本 ===

CHAPTER_WITH_FORESHADOWS = """夜色浓重,沈夜走进那间神秘的古董店。
柜台后站着一个未知的老人,他的眼神诡异而深邃。
"你来晚了。"老人低声说,似乎在等待某个秘密的揭晓。
沈夜注意到墙上挂着一幅奇怪的画,画中隐藏着一个古怪的符号。
离开时,他悄悄把符号记在心里,这是日后解开真相的关键线索。"""

CHAPTER_WITH_PAYOFF = """沈夜终于明白了。
原来那幅画上的符号,正是开启亡灵银行的钥匙!
真相大白,一切谜团都水落石出。
老人当年的话有了新的解释,指向他真正的身份。"""

CHAPTER_EMPTY = """沈夜起床,刷牙,吃饭,出门。
天气晴朗,鸟语花香。
他走在街上,看到朋友打了个招呼。
然后回家,睡觉。"""


class TestHeuristicExtraction:
    def test_extracts_plant_from_keywords(self, extractor):
        """启发式从关键词提取埋伏笔"""
        result = extractor._extract_heuristic(1, CHAPTER_WITH_FORESHADOWS)
        # 应至少提取到 1 条 planted
        assert len(result.planted) >= 1
        # 每条都有描述
        for ext in result.planted:
            assert ext.description
            assert ext.action == "plant"

    def test_extracts_pay_from_keywords(self, extractor):
        """启发式从关键词提取回收"""
        result = extractor._extract_heuristic(5, CHAPTER_WITH_PAYOFF)
        assert len(result.paid) >= 1

    def test_empty_chapter_returns_empty(self, extractor):
        """无明显伏笔的章节返回空"""
        result = extractor._extract_heuristic(1, CHAPTER_EMPTY)
        # 可能会有少量误判,但应该不多
        assert len(result.planted) <= 1

    def test_heuristic_limits_results(self, extractor):
        """启发式限制每类最多 5 条"""
        # 构造含大量伏笔关键词的内容
        content = "。".join([f"这里有神秘的伏笔{i}" for i in range(20)])
        result = extractor._extract_heuristic(1, content)
        assert len(result.planted) <= 5

    def test_heuristic_detects_type(self, extractor):
        """启发式判断明/暗伏笔"""
        content = "他悄悄隐藏了一个秘密,无人察觉。又埋下了一条明面上的线索。"
        result = extractor._extract_heuristic(1, content)
        # 至少检测到一条暗伏笔
        has_an = any(ext.type == "暗" for ext in result.planted)
        assert has_an


class TestPlanBasedExtraction:
    @pytest.mark.asyncio
    async def test_extract_from_plan_uses_plant_list(self, extractor):
        """有大纲时直接采用大纲的 foreshadows_plant"""
        plan = ChapterPlan(
            chapter_num=1,
            beat="测试",
            foreshadows_plant=["主角的神秘身世", "古董店的秘密"],
            foreshadows_pay=["上一章的悬念"],
        )
        result = await extractor.extract_from_chapter(1, "正文内容", plan=plan)
        assert isinstance(result, ExtractResult)
        assert len(result.planted) == 2
        assert len(result.paid) == 1
        assert result.model_used == "plan"

    @pytest.mark.asyncio
    async def test_extract_from_plan_empty_returns_empty(self, extractor):
        """大纲无伏笔字段时返回空"""
        plan = ChapterPlan(chapter_num=1, beat="测试")
        result = await extractor.extract_from_chapter(1, "正文", plan=plan)
        assert len(result.planted) == 0
        assert len(result.paid) == 0


class TestLLMExtraction:
    @pytest.mark.asyncio
    async def test_llm_extracts_foreshadows(self, extractor):
        """LLM 正常提取"""
        llm_output = json.dumps({
            "planted": [
                {"description": "主角手腕上的胎记", "type": "暗", "priority": "high"},
                {"description": "古董店老人的身份", "type": "明", "priority": "normal"},
            ],
            "advanced": [
                {"description": "画中符号的含义"},
            ],
            "paid": [
                {"description": "上章提到的神秘声音来源"},
            ],
        }, ensure_ascii=False)

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 800))
        extractor.gateway = mock_gateway

        result = await extractor._extract_with_llm(1, CHAPTER_WITH_FORESHADOWS)
        assert len(result.planted) == 2
        assert result.planted[0].description == "主角手腕上的胎记"
        assert result.planted[0].priority == "high"
        assert result.planted[0].type == "暗"
        assert len(result.advanced) == 1
        assert len(result.paid) == 1

    @pytest.mark.asyncio
    async def test_llm_with_markdown_wrapper(self, extractor):
        """LLM 输出被 markdown 包裹"""
        llm_output = f"```json\n{json.dumps({'planted': [{'description': 'test', 'type': '明', 'priority': 'normal'}]})}\n```"
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 100))
        extractor.gateway = mock_gateway

        result = await extractor._extract_with_llm(1, "内容")
        assert len(result.planted) == 1
        assert result.planted[0].description == "test"

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_empty(self, extractor):
        """LLM 输出非 JSON 时返回空结果(不抛异常)"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("这不是 JSON", 50))
        extractor.gateway = mock_gateway

        result = await extractor._extract_with_llm(1, "内容")
        assert len(result.planted) == 0
        assert result.model_used != "heuristic"  # 还是标记为 LLM 模型

    @pytest.mark.asyncio
    async def test_llm_truncates_long_content(self, extractor):
        """超长内容被截断"""
        long_content = "a" * 10000
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=('{"planted":[]}', 10))
        extractor.gateway = mock_gateway

        await extractor._extract_with_llm(1, long_content)
        # 验证调用时 content 被截断
        call_args = mock_gateway.generate.call_args
        user_prompt = call_args.kwargs.get("user_prompt", "")
        assert "中间省略" in user_prompt
        assert len(user_prompt) < 10000


class TestApplyToManager:
    def test_apply_plants_new_foreshadows(self, extractor, manager):
        """应用 planted 到 manager"""
        result = ExtractResult(
            chapter_num=1,
            planted=[
                ExtractedForeshadow(description="主角的神秘身世", type="明"),
                ExtractedForeshadow(description="古董店的隐藏秘密", type="暗", priority="high"),
            ],
        )
        stats = extractor.apply_to_manager(result, manager)
        assert stats["planted"] == 2
        assert len(manager.get_active()) == 2

    def test_apply_dedupes_similar_foreshadows(self, extractor, manager):
        """相似描述去重"""
        manager.plant("主角的神秘身世", chapter_num=1)

        result = ExtractResult(
            chapter_num=2,
            planted=[
                ExtractedForeshadow(description="主角神秘身世"),  # 相似
                ExtractedForeshadow(description="完全不同的伏笔"),
            ],
        )
        stats = extractor.apply_to_manager(result, manager)
        assert stats["planted"] == 1
        assert stats["skipped"] == 1

    def test_apply_pays_matching_foreshadow(self, extractor, manager):
        """pay 匹配已有 planted 伏笔"""
        eid = manager.plant("古董店的秘密", chapter_num=1)

        result = ExtractResult(
            chapter_num=5,
            paid=[ExtractedForeshadow(description="古董店的秘密揭晓")],
        )
        stats = extractor.apply_to_manager(result, manager)
        assert stats["paid"] == 1
        # 验证状态已变为 paid
        for e in manager._entries:
            if e.id == eid:
                assert e.status == "paid"
                assert e.paid_chapter == 5
                break

    def test_apply_advances_matching_foreshadow(self, extractor, manager):
        """advance 匹配 planted 伏笔"""
        manager.plant("神秘符号", chapter_num=1)

        result = ExtractResult(
            chapter_num=3,
            advanced=[ExtractedForeshadow(description="神秘符号的线索")],
        )
        stats = extractor.apply_to_manager(result, manager)
        assert stats["advanced"] == 1
        # 验证状态已变为 building
        for e in manager._entries:
            if e.description == "神秘符号":
                assert e.status == "building"
                break

    def test_apply_pay_no_match_skipped(self, extractor, manager):
        """pay 无匹配时跳过"""
        result = ExtractResult(
            chapter_num=5,
            paid=[ExtractedForeshadow(description="不存在的伏笔")],
        )
        stats = extractor.apply_to_manager(result, manager)
        assert stats["paid"] == 0
        assert stats["skipped"] == 1


class TestSimilarityMatching:
    def test_find_similar_high_overlap(self, extractor, manager):
        """高重合度的描述视为相似"""
        manager.plant("主角神秘身世的秘密", chapter_num=1)
        entry = extractor._find_similar(manager, "主角神秘身世", statuses=("planted",))
        assert entry is not None

    def test_find_similar_low_overlap_returns_none(self, extractor, manager):
        """低重合度返回 None"""
        manager.plant("主角的神秘身世", chapter_num=1)
        entry = extractor._find_similar(manager, "完全不同的内容", statuses=("planted",))
        assert entry is None

    def test_find_similar_respects_status_filter(self, extractor, manager):
        """只匹配指定状态的伏笔"""
        eid = manager.plant("主角身世", chapter_num=1)
        manager.pay(eid, chapter_num=5)

        # paid 状态不应匹配 planted 过滤
        entry = extractor._find_similar(manager, "主角身世", statuses=("planted",))
        assert entry is None

        # paid 状态应匹配 paid 过滤
        entry = extractor._find_similar(manager, "主角身世", statuses=("paid",))
        assert entry is not None


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_extract_and_apply_integration(self, tmp_config):
        """端到端集成测试"""
        # 先手动埋一个伏笔
        manager = ForeshadowManager(tmp_config.resolve_data_dir(1))
        manager.plant("古董店的秘密", chapter_num=1)

        # 第 5 章回收它
        result, stats = await extract_and_apply_foreshadows(
            tmp_config, novel_id=1, chapter_num=5,
            content=CHAPTER_WITH_PAYOFF,
            plan=None, gateway=None,
        )
        # 启发式应该能提取到一些内容
        assert isinstance(result, ExtractResult)
        assert isinstance(stats, dict)


class TestExtractFromChapterRouting:
    @pytest.mark.asyncio
    async def test_route_to_plan_when_plan_has_foreshadows(self, extractor):
        """有大纲伏笔字段时走 plan 路径"""
        plan = ChapterPlan(
            chapter_num=1, beat="test",
            foreshadows_plant=["plan 伏笔"],
        )
        result = await extractor.extract_from_chapter(1, "内容", plan=plan)
        assert result.model_used == "plan"
        assert len(result.planted) == 1

    @pytest.mark.asyncio
    async def test_route_to_llm_when_gateway_available(self, extractor):
        """无大纲但有 gateway 时走 LLM 路径"""
        llm_output = json.dumps({
            "planted": [{"description": "llm 伏笔", "type": "明", "priority": "normal"}],
            "advanced": [], "paid": [],
        }, ensure_ascii=False)
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 200))
        extractor.gateway = mock_gateway

        result = await extractor.extract_from_chapter(1, "内容", plan=None)
        assert result.model_used != "heuristic"
        assert len(result.planted) == 1

    @pytest.mark.asyncio
    async def test_route_to_heuristic_when_no_gateway(self, extractor):
        """无 gateway 时走启发式"""
        result = await extractor.extract_from_chapter(1, CHAPTER_WITH_FORESHADOWS, plan=None)
        assert result.model_used == "heuristic"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_heuristic(self, extractor):
        """LLM 失败降级到启发式"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(side_effect=Exception("API 错误"))
        extractor.gateway = mock_gateway

        result = await extractor.extract_from_chapter(1, CHAPTER_WITH_FORESHADOWS, plan=None)
        assert result.model_used == "heuristic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
