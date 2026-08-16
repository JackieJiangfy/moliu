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

    def test_update_bible_heuristic_relations(self, memory):
        """同步兜底版应从 key_characters 拼装出场关系"""
        meta = _make_meta(5, key_events=["大战爆发"])
        meta.key_characters = ["李逸", "苏婉", "黑衣人"]
        bible = memory.update_bible_after_chapter(5, meta, "正文")
        assert any("李逸" in r and "苏婉" in r for r in bible.character_relations)
        assert bible.last_updated_chapter == 5


class TestBibleLLMUpdate:
    """问题1: Story Bible LLM 增量提取测试"""

    @pytest.mark.asyncio
    async def test_async_update_without_gateway_falls_back(self, memory):
        """无 gateway 时,异步版应回退到同步(只更新 key_events + 启发式同场关系)"""
        meta = _make_meta(3, key_events=["黑衣人现身"])
        bible = await memory.update_bible_after_chapter_async(3, meta, "正文内容")
        assert any("黑衣人现身" in e for e in bible.key_events)
        # 无 gateway 不会 LLM 提取,但同步版启发式同场关系会写
        assert any("主角" in r and "配角" in r for r in bible.character_relations)
        assert bible.world_facts == []
        assert bible.open_promises == []

    @pytest.mark.asyncio
    async def test_async_update_with_llm_extracts_facts(self, memory):
        """有 gateway 时,异步版应调用 LLM 提取三类事实"""
        meta = _make_meta(7, key_events=["宝物现世"])
        meta.key_characters = ["李逸", "苏婉"]

        llm_output = json.dumps({
            "world_facts": ["昆仑山是修仙圣地", "守墓人是隐世高人"],
            "character_relations": ["李逸与苏婉结为道侣", "李逸答应苏婉三年内归来"],
            "open_promises": ["李逸承诺三年后归来", "守墓人隐藏身份未揭"],
        }, ensure_ascii=False)

        gw = MagicMock()
        gw.generate = AsyncMock(return_value=(llm_output, 500))
        memory.gateway = gw

        bible = await memory.update_bible_after_chapter_async(
            7, meta, "正文内容 " * 50,
        )
        # key_events 同步更新
        assert any("宝物现世" in e for e in bible.key_events)
        # world_facts LLM 提取
        assert any("昆仑山" in f for f in bible.world_facts)
        # character_relations 加 [第7章] 前缀
        assert any("道侣" in r and "第7章" in r for r in bible.character_relations)
        # open_promises 直接合并
        assert any("三年后归来" in p for p in bible.open_promises)

    @pytest.mark.asyncio
    async def test_async_update_llm_failure_falls_back(self, memory):
        """LLM 调用失败时,异步版应回退到同步版,不阻断"""
        meta = _make_meta(8, key_events=["大战爆发"])
        meta.key_characters = ["李逸", "黑衣人"]

        gw = MagicMock()
        gw.generate = AsyncMock(side_effect=RuntimeError("API 不可用"))
        memory.gateway = gw

        bible = await memory.update_bible_after_chapter_async(
            8, meta, "正文内容 " * 50,
        )
        # 仍同步更新 key_events
        assert any("大战爆发" in e for e in bible.key_events)
        # 启发式同场关系也被记录(因为 update_bible_after_chapter_async 先调同步版)
        assert any("李逸" in r and "黑衣人" in r for r in bible.character_relations)

    def test_parse_bible_facts_json_valid(self):
        """LLM JSON 输出正常解析"""
        raw = """```json
{
  "world_facts": ["南海有龙宫"],
  "character_relations": ["龙王与主角结盟"],
  "open_promises": ["龙王承诺借兵"]
}
```"""
        facts = LayeredMemory._parse_bible_facts_json(raw, chapter_num=10)
        assert facts.world_facts == ["南海有龙宫"]
        assert facts.character_relations == ["龙王与主角结盟"]
        assert facts.open_promises == ["龙王承诺借兵"]

    def test_parse_bible_facts_json_invalid_returns_empty(self):
        """LLM 输出非 JSON 时返回空事实(不抛异常)"""
        raw = "我无法提取事实,这一章没有新信息。"
        facts = LayeredMemory._parse_bible_facts_json(raw, chapter_num=11)
        assert facts.world_facts == []
        assert facts.character_relations == []
        assert facts.open_promises == []

    def test_parse_bible_facts_json_missing_fields(self):
        """LLM JSON 缺字段时用空数组兜底"""
        raw = '{"world_facts": ["只提取了世界观"]}'
        facts = LayeredMemory._parse_bible_facts_json(raw, chapter_num=12)
        assert facts.world_facts == ["只提取了世界观"]
        assert facts.character_relations == []
        assert facts.open_promises == []

    @pytest.mark.asyncio
    async def test_async_update_dedupes_facts(self, memory):
        """同一事实重复提取应去重"""
        meta = _make_meta(9, key_events=["第一章事件"])
        meta.key_characters = ["A", "B"]

        llm_output = json.dumps({
            "world_facts": ["昆仑山是修仙圣地"],
            "character_relations": ["A与B结盟"],
            "open_promises": [],
        }, ensure_ascii=False)
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=(llm_output, 100))
        memory.gateway = gw

        # 第一次更新
        await memory.update_bible_after_chapter_async(9, meta, "正文 " * 50)
        # 第二次同样事实
        await memory.update_bible_after_chapter_async(10, meta, "正文 " * 50)
        bible = memory.load_bible()
        # world_facts 不应重复
        count = sum(1 for f in bible.world_facts if "昆仑山" in f)
        assert count == 1


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

    @pytest.mark.asyncio
    async def test_llm_arc_summary_json_format(self, memory, tmp_config):
        """问题7: LLM 输出 JSON 格式时正确解析"""
        for i in range(1, 11):
            meta = _make_meta(i, summary=f"第{i}章摘要", key_events=[f"事件{i}"])
            _save_chapter_meta(tmp_config, i, meta)

        import json
        llm_output = json.dumps({
            "summary": "主角在第1-10章中完成了从普通人到觉醒者的转变。",
            "key_events": ["主角觉醒能力", "与反派首次交锋", "加入守护者组织"],
            "character_changes": ["主角 — 从普通人变为觉醒者"],
            "open_threads": ["反派的真实目的尚未揭晓", "主角的师父下落不明"],
        }, ensure_ascii=False)

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_output, 500))
        memory.gateway = mock_gateway

        arc = await memory.generate_arc_summary(1, 1, 10)
        assert arc.arc_id == 1
        assert "主角" in arc.summary
        assert len(arc.key_events) == 3
        assert any("觉醒" in e for e in arc.key_events)
        assert len(arc.character_changes) == 1
        assert len(arc.open_threads) == 2

    def test_parse_arc_json_plain(self):
        """问题7: 纯 JSON 字符串正确解析"""
        from moliu.memory.layered import LayeredMemory
        import json

        text = json.dumps({
            "summary": "测试总结",
            "key_events": ["事件A", "事件B"],
            "character_changes": ["角色X变化"],
            "open_threads": ["悬念1"],
        }, ensure_ascii=False)

        s, events, changes, threads = LayeredMemory._parse_arc_llm_output(text)
        assert s == "测试总结"
        assert events == ["事件A", "事件B"]
        assert changes == ["角色X变化"]
        assert threads == ["悬念1"]

    def test_parse_arc_json_with_markdown_wrapper(self):
        """问题7: JSON 被 markdown 代码块包裹时也能解析"""
        from moliu.memory.layered import LayeredMemory
        import json

        inner = json.dumps({
            "summary": "带包裹的总结",
            "key_events": ["事件1"],
            "character_changes": [],
            "open_threads": [],
        }, ensure_ascii=False)
        text = f"```json\n{inner}\n```"

        s, events, changes, threads = LayeredMemory._parse_arc_llm_output(text)
        assert s == "带包裹的总结"
        assert events == ["事件1"]

    def test_parse_arc_fallback_to_legacy_format(self):
        """问题7: JSON 解析失败时回退到【】标记格式"""
        from moliu.memory.layered import LayeredMemory

        # 旧的【】格式
        text = """【阶段总结】
旧格式总结内容。

【关键事件】
1. 旧事件A发生了
2. 旧事件B结束了

【未决线索】
1. 旧悬念仍未解"""

        s, events, changes, threads = LayeredMemory._parse_arc_llm_output(text)
        assert "旧格式总结" in s
        assert any("旧事件A" in e for e in events)
        assert any("旧悬念" in t for t in threads)

    def test_parse_arc_json_partial_fields(self):
        """问题7: JSON 缺少部分字段时不报错"""
        from moliu.memory.layered import LayeredMemory
        import json

        text = json.dumps({
            "summary": "只有总结",
            # 缺少 key_events/character_changes/open_threads
        }, ensure_ascii=False)

        s, events, changes, threads = LayeredMemory._parse_arc_llm_output(text)
        assert s == "只有总结"
        assert events == []
        assert changes == []
        assert threads == []

    def test_parse_arc_json_invalid_returns_empty(self):
        """问题7: 既不是 JSON 也不是【】格式时返回空"""
        from moliu.memory.layered import LayeredMemory

        text = "这是一段无法解析的随机文本"
        s, events, changes, threads = LayeredMemory._parse_arc_llm_output(text)
        assert s == ""
        assert events == []


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
