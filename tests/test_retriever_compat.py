"""Retriever 兼容层测试

验证旧代码 `from moliu.memory.retriever import Retriever` 仍可用,
且行为等价于 StructuredAssembler。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from moliu.config import Config
from moliu.context.assembler import StructuredAssembler
from moliu.memory.retriever import Retriever


class TestRetrieverCompat:
    """Retriever 向后兼容性"""

    def test_retriever_is_subclass_of_assembler(self):
        """Retriever 应是 StructuredAssembler 的子类"""
        assert issubclass(Retriever, StructuredAssembler)

    def test_retriever_construction_without_memory(self, tmp_path: Path):
        """不带 memory 参数也能构造(老代码可能直接 Retriever(config))"""
        cfg = Config()
        cfg.project_dir = tmp_path
        # 不应抛异常
        r = Retriever(cfg)
        assert isinstance(r, StructuredAssembler)
        assert r.config is cfg

    def test_retriever_construction_with_memory(self, tmp_path: Path):
        """带 memory 参数也能构造 — memory 被存为属性但不再使用"""
        cfg = Config()
        cfg.project_dir = tmp_path
        sentinel = object()  # 任意非 None 占位
        r = Retriever(cfg, memory=sentinel)  # type: ignore[arg-type]
        assert r.memory is sentinel

    def test_retriever_inherits_assembler_methods(self, tmp_path: Path):
        """Retriever 应继承 StructuredAssembler 的所有公开方法"""
        cfg = Config()
        cfg.project_dir = tmp_path
        r = Retriever(cfg)

        # 抽几个 StructuredAssembler 的核心方法验证可访问
        for attr in ("assemble", "inject_graph_context", "novel_id"):
            assert hasattr(r, attr), f"Retriever 缺失属性: {attr}"

    def test_retriever_uses_same_novel_id_default(self, tmp_path: Path):
        """默认 novel_id 应与 StructuredAssembler 一致(=1)"""
        cfg = Config()
        cfg.project_dir = tmp_path
        r = Retriever(cfg)
        assert r.novel_id == 1

    @pytest.mark.asyncio
    async def test_retriever_assemble_equivalent_to_assembler(self, tmp_path: Path):
        """同一配置下,Retriever 与 StructuredAssembler 行为一致"""
        cfg = Config()
        cfg.project_dir = tmp_path
        # 准备最小数据:一张角色卡
        from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting
        chars_dir = cfg.resolve_novel_data_dir(1) / "characters"
        chars_dir.mkdir(parents=True, exist_ok=True)
        CharacterCard(name="测试角色").to_yaml(chars_dir / "测试角色.yaml")

        r = Retriever(cfg)
        a = StructuredAssembler(cfg, novel_id=1)

        narrator = NarratorCard(narrative_pov="第三人称", narrative_tense="过去时")
        world = WorldSetting(era="测试时代")
        chars = [CharacterCard(name="测试角色")]

        ctx_r = await r.assemble(
            chapter_num=1, beat="测试",
            characters=chars, world=world,
            narrator=narrator, last_emotion="平静",
        )
        ctx_a = await a.assemble(
            chapter_num=1, beat="测试",
            characters=chars, world=world,
            narrator=narrator, last_emotion="平静",
        )

        # 上下文类型应一致
        assert type(ctx_r).__name__ == type(ctx_a).__name__
