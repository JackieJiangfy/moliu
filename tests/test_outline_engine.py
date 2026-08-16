"""章级大纲引擎 (P0-2) 测试"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from moliu.config import Config
from moliu.data.schemas import VolumeIndex, VolumePlan
from moliu.engines.outline_engine import (
    DEFAULT_EMOTION_PATTERN,
    DEFAULT_RHYTHM_PATTERN,
    ChapterOutlineEngine,
    OutlineGenResult,
)


@pytest.fixture
def tmp_config(tmp_path):
    config = Config()
    config.project_dir = tmp_path
    config.data_dir = Path("data")
    config.output_dir = Path("output/chapters")
    (tmp_path / "data" / "novels" / "1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "novels" / "1" / "chapters").mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def volume_setup(tmp_config):
    """创建一个测试卷 (第 1-20 章)"""
    index_dir = tmp_config.resolve_data_dir(1) / "volumes"
    index_dir.mkdir(parents=True, exist_ok=True)
    index = VolumeIndex(
        novel_title="测试小说",
        volumes=[
            VolumePlan(
                id=1, name="卷一·起点",
                chapter_start=1, chapter_end=20,
                summary="主角觉醒能力,加入守护者组织",
            ),
            VolumePlan(
                id=2, name="卷二·成长",
                chapter_start=21, chapter_end=40,
                summary="主角与反派首次交锋",
            ),
        ],
    )
    index.to_json(index_dir / "index.json")
    return tmp_config


@pytest.fixture
def engine(volume_setup):
    return ChapterOutlineEngine(volume_setup, novel_id=1)


class TestHeuristicGeneration:
    @pytest.mark.asyncio
    async def test_generate_heuristic_fills_all_chapters(self, engine):
        """启发式生成覆盖所有章节"""
        result = await engine.generate_for_volume(1)
        assert result.volume_id == 1
        assert result.chapter_start == 1
        assert result.chapter_end == 20
        assert len(result.plans) == 20
        assert result.model_used == "heuristic"

        # 每章都有 beat
        for p in result.plans:
            assert p.beat, f"第 {p.chapter_num} 章 beat 为空"
            assert p.chapter_type in {"opening", "normal", "climax", "transition", "epilogue"}
            assert p.emotion

    @pytest.mark.asyncio
    async def test_heuristic_has_rhythm_pattern(self, engine):
        """启发式生成遵循节奏模板"""
        result = await engine.generate_for_volume(1)
        # 第 1 章应该是 opening (idx=0)
        assert result.plans[0].chapter_type == "opening"
        # 第 7 章应该是 climax (idx=6)
        assert result.plans[6].chapter_type == "climax"
        # 第 14 章应该是 climax (idx=13)
        assert result.plans[13].chapter_type == "climax"
        # 所有章节类型都符合 DEFAULT_RHYTHM_PATTERN
        for i, p in enumerate(result.plans):
            expected = DEFAULT_RHYTHM_PATTERN[i % len(DEFAULT_RHYTHM_PATTERN)]
            assert p.chapter_type == expected, f"第 {p.chapter_num} 章类型应为 {expected},实际 {p.chapter_type}"


class TestPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, engine):
        """保存后重新加载,数据一致"""
        await engine.generate_for_volume(1)
        loaded = engine.load_volume_outline(1)
        assert len(loaded) == 20
        assert loaded[0].chapter_num == 1
        assert loaded[19].chapter_num == 20

    @pytest.mark.asyncio
    async def test_cached_when_not_forced(self, engine):
        """非 force 模式下,已存在大纲直接返回缓存"""
        first = await engine.generate_for_volume(1)
        assert first.model_used == "heuristic"

        # 二次调用不 force,应返回 cached
        second = await engine.generate_for_volume(1, force=False)
        assert second.model_used == "cached"
        assert len(second.plans) == 20

    @pytest.mark.asyncio
    async def test_force_regenerates(self, engine):
        """force=True 时重新生成"""
        first = await engine.generate_for_volume(1)
        # 修改一个字段
        engine.update_chapter_plan(1, beat="手动修改")
        loaded = engine.load_volume_outline(1)
        assert any(p.beat == "手动修改" for p in loaded)

        # force 重生成应覆盖
        await engine.generate_for_volume(1, force=True)
        loaded = engine.load_volume_outline(1)
        assert not any(p.beat == "手动修改" for p in loaded)


class TestChapterPlanLookup:
    @pytest.mark.asyncio
    async def test_get_chapter_plan_finds_across_volumes(self, engine):
        """跨卷查找章节大纲"""
        # 生成卷1的大纲(1-20)
        await engine.generate_for_volume(1)
        plan = engine.get_chapter_plan(15)
        assert plan is not None
        assert plan.chapter_num == 15

    @pytest.mark.asyncio
    async def test_get_chapter_plan_returns_none_for_missing(self, engine):
        """无大纲时返回 None"""
        assert engine.get_chapter_plan(999) is None

    @pytest.mark.asyncio
    async def test_update_chapter_plan(self, engine):
        """更新单章字段"""
        await engine.generate_for_volume(1)
        updated = engine.update_chapter_plan(
            10, beat="修改后的beat", emotion="震撼",
        )
        assert updated is not None
        assert updated.beat == "修改后的beat"
        assert updated.emotion == "震撼"

        # 重新加载验证持久化
        loaded = engine.load_volume_outline(1)
        p10 = next(p for p in loaded if p.chapter_num == 10)
        assert p10.beat == "修改后的beat"

    @pytest.mark.asyncio
    async def test_mark_chapter_status(self, engine):
        """更新章节状态"""
        await engine.generate_for_volume(1)
        engine.mark_chapter_status(5, "generating")
        plan = engine.get_chapter_plan(5)
        assert plan.status == "generating"

        engine.mark_chapter_status(5, "completed")
        plan = engine.get_chapter_plan(5)
        assert plan.status == "completed"


class TestLLMGeneration:
    @pytest.mark.asyncio
    async def test_llm_generates_plans(self, engine, volume_setup):
        """LLM 生成正常路径"""
        # 构造 LLM 输出 — 20 章的 JSON 数组
        llm_plans = []
        for i, ch in enumerate(range(1, 21)):
            rhythm = DEFAULT_RHYTHM_PATTERN[i % len(DEFAULT_RHYTHM_PATTERN)]
            llm_plans.append({
                "chapter_num": ch,
                "title": f"第{ch}章标题",
                "beat": f"第{ch}章的 beat 描述,推进主角觉醒能力",
                "emotion": DEFAULT_EMOTION_PATTERN[i % len(DEFAULT_EMOTION_PATTERN)],
                "chapter_type": rhythm,
                "key_events": [f"事件{ch}-1", f"事件{ch}-2"],
                "foreshadows_plant": [f"伏笔{ch}"],
                "foreshadows_pay": [],
            })
        llm_output = json.dumps(llm_plans, ensure_ascii=False)

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 1500))
        engine.gateway = mock_gateway

        result = await engine.generate_for_volume(1, force=True)
        assert result.model_used != "heuristic"
        assert len(result.plans) == 20
        assert result.plans[0].beat == "第1章的 beat 描述,推进主角觉醒能力"
        assert result.plans[0].key_events == ["事件1-1", "事件1-2"]

    @pytest.mark.asyncio
    async def test_llm_with_markdown_wrapper(self, engine):
        """LLM 输出被 markdown 包裹时能正确解析"""
        llm_plans = [
            {"chapter_num": i, "beat": f"beat{i}", "chapter_type": "normal"}
            for i in range(1, 21)
        ]
        llm_output = f"```json\n{json.dumps(llm_plans, ensure_ascii=False)}\n```"

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 1200))
        engine.gateway = mock_gateway

        result = await engine.generate_for_volume(1, force=True)
        assert len(result.plans) == 20

    @pytest.mark.asyncio
    async def test_llm_missing_chapters_filled(self, engine):
        """LLM 输出缺少部分章节时,用启发式补全"""
        # 只返回 5 章
        llm_plans = [
            {"chapter_num": i, "beat": f"llm beat{i}", "chapter_type": "normal"}
            for i in range(1, 6)
        ]
        llm_output = json.dumps(llm_plans, ensure_ascii=False)

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 500))
        engine.gateway = mock_gateway

        result = await engine.generate_for_volume(1, force=True)
        assert len(result.plans) == 20
        # 前 5 章用 LLM 的 beat
        assert result.plans[0].beat == "llm beat1"
        # 第 6-20 章用启发式
        assert result.plans[5].beat  # 非空

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_heuristic(self, engine):
        """LLM 调用失败时降级到启发式"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(side_effect=Exception("API 错误"))
        engine.gateway = mock_gateway

        result = await engine.generate_for_volume(1, force=True)
        assert result.model_used == "heuristic"
        assert len(result.plans) == 20

    @pytest.mark.asyncio
    async def test_llm_invalid_json_falls_back(self, engine):
        """LLM 输出非 JSON 时降级"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=("这不是 JSON", 100))
        engine.gateway = mock_gateway

        result = await engine.generate_for_volume(1, force=True)
        assert result.model_used == "heuristic"


class TestStatusPreservation:
    @pytest.mark.asyncio
    async def test_preserves_completed_status_on_regenerate(self, engine):
        """重新生成时保留已生成章节的 status"""
        await engine.generate_for_volume(1)
        # 标记第 5、10 章为 completed
        engine.mark_chapter_status(5, "completed")
        engine.mark_chapter_status(10, "completed")

        # 强制重新生成
        await engine.generate_for_volume(1, force=True)
        # 第 5、10 章的 status 应保留为 completed
        p5 = engine.get_chapter_plan(5)
        p10 = engine.get_chapter_plan(10)
        assert p5.status == "completed"
        assert p10.status == "completed"
        # 第 1 章应该被重置为 planned
        p1 = engine.get_chapter_plan(1)
        assert p1.status == "planned"


class TestCoverageStats:
    @pytest.mark.asyncio
    async def test_coverage_with_no_outlines(self, engine):
        """无大纲时覆盖率为 0"""
        stats = engine.get_outline_coverage()
        assert stats["total_planned"] == 0
        assert stats["total_generated"] == 0
        # 两个卷都缺失
        assert len(stats["missing_volumes"]) == 2

    @pytest.mark.asyncio
    async def test_coverage_after_generation(self, engine):
        """生成大纲后覆盖率正确"""
        await engine.generate_for_volume(1)
        engine.mark_chapter_status(1, "completed")
        engine.mark_chapter_status(2, "completed")

        stats = engine.get_outline_coverage()
        assert stats["total_planned"] == 20
        assert stats["total_generated"] == 2
        assert 1 in stats["covered_volumes"]
        assert 2 in stats["missing_volumes"]


class TestMultiVolume:
    @pytest.mark.asyncio
    async def test_list_all_plans_across_volumes(self, engine):
        """跨卷列出所有大纲"""
        await engine.generate_for_volume(1)
        await engine.generate_for_volume(2)

        all_plans = engine.list_all_plans()
        assert 1 in all_plans
        assert 2 in all_plans
        assert len(all_plans[1]) == 20
        assert len(all_plans[2]) == 20


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_generate_nonexistent_volume_raises(self, engine):
        """不存在的卷 ID 抛出 ValueError"""
        with pytest.raises(ValueError):
            await engine.generate_for_volume(999)

    @pytest.mark.asyncio
    async def test_generate_invalid_range_raises(self, volume_setup):
        """章节范围无效时抛出 ValueError"""
        # 修改卷 2 使范围无效
        idx_path = volume_setup.resolve_data_dir(1) / "volumes" / "index.json"
        vidx = VolumeIndex.from_json(idx_path)
        vidx.volumes[1].chapter_start = 30
        vidx.volumes[1].chapter_end = 20  # 反了
        vidx.to_json(idx_path)

        engine = ChapterOutlineEngine(volume_setup, novel_id=1)
        with pytest.raises(ValueError):
            await engine.generate_for_volume(2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
