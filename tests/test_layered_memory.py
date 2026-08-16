"""分层记忆系统 (P0-1) 测试

测试 LayeredMemory 的核心功能:
- 阶段摘要生成 (启发式 + LLM 模拟)
- Story Bible 增量更新 + 重建
- 上下文装配
- 失败优雅降级
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from moliu.config import Config
from moliu.data.schemas import ChapterMeta
from moliu.memory.layered import (
    ARC_SIZE,
    ArcSummary,
    LayeredMemory,
    StoryBible,
)


@pytest.fixture
def tmp_config(tmp_path):
    """临时项目目录的 Config"""
    config = Config()
    config.project_dir = tmp_path
    config.data_dir = Path("data")
    config.output_dir = Path("output/chapters")
    # 创建小说数据目录
    (tmp_path / "data" / "novels" / "1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "novels" / "1" / "chapters").mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def memory(tmp_config):
    return LayeredMemory(tmp_config, novel_id=1)


def _make_meta(chapter_num: int, summary: str = "", key_events: list[str] | None = None) -> ChapterMeta:
    """构造测试用 ChapterMeta"""
    return ChapterMeta(
        chapter_num=chapter_num,
        word_count=2000,
        tokens_used=1000,
        emotion="紧张",
        summary=summary,
        key_characters=["主角", "配角"],
        key_events=key_events or [],
    )


def _save_chapter_meta(tmp_config: Config, num: int, meta: ChapterMeta):
    """把章节 meta 写入到 output 目录"""
    out_dir = tmp_config.resolve_output_dir(1) / Config.chapter_dir_name(num)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta.to_json(out_dir / "meta.json")


class TestStoryBible:
    def test_empty_bible_to_context_returns_empty(self):
        bible = StoryBible(novel_id=1)
        assert bible.to_context() == ""

    def test_bible_with_events_renders_sections(self):
        bible = StoryBible(
            novel_id=1,
            key_events=["[第1章] 主角觉醒", "[第2章] 遇到反派"],
            world_facts=["世界A", "世界B"],
            open_promises=["承诺1"],
            character_relations=["A↔B 师徒"],
        )
        ctx = bible.to_context()
        assert "已发生关键事件" in ctx
        assert "[第1章] 主角觉醒" in ctx
        assert "世界观已确立事实" in ctx
        assert "未解悬念" in ctx
        assert "角色关系演化" in ctx

    def test_bible_serialization_roundtrip(self):
        bible = StoryBible(
            novel_id=1,
            key_events=["event1"],
            world_facts=["fact1"],
            last_updated_chapter=5,
        )
        d = bible.to_dict()
        restored = StoryBible.from_dict(d)
        assert restored.key_events == ["event1"]
        assert restored.world_facts == ["fact1"]
        assert restored.last_updated_chapter == 5


class TestLayeredMemoryPersistence:
    def test_save_and_load_bible(self, memory):
        bible = StoryBible(
            novel_id=1,
            key_events=["test event"],
            world_facts=["test fact"],
            last_updated_chapter=10,
        )
        memory.save_bible(bible)

        loaded = memory.load_bible()
        assert loaded.key_events == ["test event"]
        assert loaded.world_facts == ["test fact"]
        assert loaded.last_updated_chapter == 10

    def test_load_missing_bible_returns_empty(self, memory):
        bible = memory.load_bible()
        assert bible.novel_id == 1
        assert bible.key_events == []

    def test_save_and_load_arc_summaries(self, memory):
        arc = ArcSummary(
            arc_id=1,
            chapter_start=1,
            chapter_end=10,
            summary="阶段1总结",
            key_events=["事件1"],
            chapter_count=10,
        )
        memory._save_arc_summary(arc)
        loaded = memory.load_arc_summaries()
        assert len(loaded) == 1
        assert loaded[0].summary == "阶段1总结"

    def test_load_recent_arcs_filters_future(self, memory):
        """load_recent_arcs 只返回 chapter_end < chapter_num 的阶段"""
        arc1 = ArcSummary(arc_id=1, chapter_start=1, chapter_end=10)
        arc2 = ArcSummary(arc_id=2, chapter_start=11, chapter_end=20)
        memory._save_arc_summary(arc1)
        memory._save_arc_summary(arc2)

        # 当前第 15 章,只应返回 arc1
        recent = memory.load_recent_arcs(15)
        assert len(recent) == 1
        assert recent[0].arc_id == 1


class TestBibleUpdate:
    def test_update_bible_appends_key_events(self, memory):
        meta = _make_meta(1, key_events=["主角觉醒能力"])
        bible = memory.update_bible_after_chapter(1, meta, "正文内容")
        assert any("主角觉醒能力" in e for e in bible.key_events)
        assert bible.last_updated_chapter == 1

    def test_update_bible_dedupes_events(self, memory):
        """同一章节同一事件多次更新不重复"""
        meta = _make_meta(1, key_events=["主角觉醒"])
        memory.update_bible_after_chapter(1, meta)
        memory.update_bible_after_chapter(1, meta)
        bible = memory.load_bible()
        # 只应有一条
        count = sum(1 for e in bible.key_events if "主角觉醒" in e)
        assert count == 1

    def test_update_bible_truncates_when_over_limit(self, memory):
        """超出 2*MAX_EVENTS 上限时丢弃最旧的事件"""
        from moliu.memory.layered import BIBLE_MAX_EVENTS
        # 写入大量事件,触发裁剪(需 > 2 * MAX_EVENTS)
        total_chapters = BIBLE_MAX_EVENTS * 3 // 2 + 10  # 约 130 章
        for ch in range(1, total_chapters + 1):
            meta = _make_meta(ch, key_events=[f"事件{ch}-a", f"事件{ch}-b"])
            memory.update_bible_after_chapter(ch, meta)
        bible = memory.load_bible()
        # 裁剪后不超过 2 * MAX_EVENTS
        assert len(bible.key_events) <= BIBLE_MAX_EVENTS * 2
        # 保留的是最新事件,最旧事件被丢弃
        assert any(f"事件{total_chapters}" in e for e in bible.key_events)
        # 第 1 章事件应该已被裁剪掉
        assert not any("事件1-a" in e for e in bible.key_events)


class TestArcSummary:
    def test_heuristic_summary_without_llm(self, memory, tmp_config):
        """无 LLM 时用启发式生成阶段摘要"""
        for i in range(1, 11):
            meta = _make_meta(i, summary=f"第{i}章摘要", key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        arc = memory._sync_generate_arc(1, 1, 10)
        assert arc.arc_id == 1
        assert arc.chapter_count == 10
        assert "第1-10章" in arc.summary
        assert len(arc.key_events) > 0

    def test_maybe_generate_arc_triggers_at_multiples(self, memory, tmp_config):
        """章节号是 ARC_SIZE 倍数时触发"""
        for i in range(1, 11):
            meta = _make_meta(i, key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        # 第 10 章应该触发
        arc = memory.maybe_generate_arc_for_chapter(10)
        assert arc is not None
        assert arc.arc_id == 1

        # 重复调用不会重新生成(幂等)
        arc2 = memory.maybe_generate_arc_for_chapter(10)
        assert arc2 is None

        # 第 5 章不触发
        arc3 = memory.maybe_generate_arc_for_chapter(5)
        assert arc3 is None

    @pytest.mark.asyncio
    async def test_llm_arc_summary(self, memory, tmp_config):
        """模拟 LLM 生成阶段摘要"""
        for i in range(1, 11):
            meta = _make_meta(i, summary=f"第{i}章摘要", key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        # 模拟 gateway
        llm_output = """【阶段总结】
主角在第1-10章中完成了从普通人到觉醒者的转变。

【关键事件】
1. 主角觉醒能力
2. 与反派首次交锋
3. 加入守护者组织

【角色变化】
1. 主角 — 从普通人变为觉醒者

【未决线索】
1. 反派的真实目的尚未揭晓
2. 主角的师父下落不明
"""
        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 500))
        memory.gateway = mock_gateway

        arc = await memory.generate_arc_summary(1, 1, 10)
        assert arc.arc_id == 1
        assert "主角" in arc.summary
        assert len(arc.key_events) >= 2
        assert any("觉醒" in e for e in arc.key_events)
        assert len(arc.open_threads) >= 1

    @pytest.mark.asyncio
    async def test_arc_summary_fallback_on_llm_failure(self, memory, tmp_config):
        """LLM 失败时回退到启发式"""
        for i in range(1, 11):
            meta = _make_meta(i, key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(side_effect=Exception("API 错误"))
        memory.gateway = mock_gateway

        arc = await memory.generate_arc_summary(1, 1, 10)
        assert arc.summary  # 启发式仍生成了内容
        assert "第1-10章" in arc.summary


class TestRebuildBible:
    def test_rebuild_from_history(self, memory, tmp_config):
        """从已存在的章节 meta 重建 Story Bible"""
        for i in range(1, 6):
            meta = _make_meta(i, key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        bible = memory.rebuild_bible_from_history()
        assert len(bible.key_events) == 5
        assert any("事件1" in e for e in bible.key_events)
        assert any("事件5" in e for e in bible.key_events)
        assert bible.last_updated_chapter == 5


class TestAssembleForChapter:
    def test_assemble_empty_when_no_data(self, memory):
        """无任何记忆数据时返回空"""
        assert memory.assemble_for_chapter(1) == ""

    def test_assemble_includes_arcs_and_bible(self, memory, tmp_config):
        """同时包含阶段摘要和 Story Bible"""
        # 准备阶段摘要
        arc = ArcSummary(
            arc_id=1,
            chapter_start=1,
            chapter_end=10,
            summary="阶段1总结",
            key_events=["阶段1事件"],
        )
        memory._save_arc_summary(arc)

        # 准备 Story Bible
        bible = StoryBible(
            novel_id=1,
            key_events=["bible 事件"],
            world_facts=["世界设定"],
        )
        memory.save_bible(bible)

        ctx = memory.assemble_for_chapter(15)
        assert "前文阶段摘要" in ctx
        assert "阶段1总结" in ctx
        assert "Story Bible" in ctx
        assert "bible 事件" in ctx

    def test_assemble_only_returns_relevant_arcs(self, memory):
        """只返回 chapter_end < chapter_num 的阶段"""
        arc1 = ArcSummary(arc_id=1, chapter_start=1, chapter_end=10, summary="阶段1")
        arc2 = ArcSummary(arc_id=2, chapter_start=11, chapter_end=20, summary="阶段2")
        memory._save_arc_summary(arc1)
        memory._save_arc_summary(arc2)

        ctx = memory.assemble_for_chapter(15)
        assert "阶段1" in ctx
        assert "阶段2" not in ctx  # arc2 的 chapter_end=20 >= 15,不应出现


class TestIntegrationWithAssembler:
    """测试 LayeredMemory 与 StructuredAssembler 的集成"""

    def test_assembler_without_layered_memory_works(self, tmp_config):
        """未传入 layered_memory 时正常工作"""
        from moliu.context.assembler import StructuredAssembler
        asm = StructuredAssembler(tmp_config, novel_id=1)
        assert asm._layered_memory is None

    def test_assembler_with_layered_memory_injects_context(self, tmp_config):
        """传入 layered_memory 后 ctx.layered_memory 有值"""
        from moliu.context.assembler import StructuredAssembler

        layered = LayeredMemory(tmp_config, novel_id=1)
        bible = StoryBible(novel_id=1, key_events=["test event"])
        layered.save_bible(bible)

        asm = StructuredAssembler(tmp_config, novel_id=1, layered_memory=layered)
        assert asm._layered_memory is layered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
