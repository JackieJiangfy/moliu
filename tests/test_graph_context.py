"""inject_graph_context 边界测试

验证内建关系图谱上下文注入对以下场景的处理:
- 空数据目录(全新小说)
- 角色出场间隔告警
- 伏笔年龄提醒 / 紧急
- 关系张力提示
- 死亡 / 离场角色不被提醒
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from moliu.config import Config
from moliu.context.assembler import StructuredAssembler
from moliu.data.schemas import (
    CharacterCard,
    CharacterState,
)


pytestmark = pytest.mark.asyncio


def _make_assembler(tmp_path: Path) -> tuple[StructuredAssembler, Config, Path]:
    """构造一个使用 tmp_path 作为项目根的 assembler"""
    cfg = Config()
    # 覆盖 project_dir 到临时目录,避免污染真实仓库
    cfg.project_dir = tmp_path
    asm = StructuredAssembler(cfg, novel_id=1)
    data_dir = cfg.resolve_novel_data_dir(1)
    return asm, cfg, data_dir


def _write_char(data_dir: Path, name: str, last_ch: int = 0, status: str = "") -> None:
    """在 data_dir/characters/ 写一张角色卡"""
    chars_dir = data_dir / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)
    card = CharacterCard(
        name=name,
        state=CharacterState(
            location="x",
            current_goal="y",
            current_emotion="z",
            status=status,
            last_chapter_appeared=last_ch,
        ),
    )
    card.to_yaml(chars_dir / f"{name}.yaml")


class TestInjectGraphContext:
    """inject_graph_context 各场景"""

    async def test_empty_data_dir(self, tmp_path):
        """全新小说 — data_dir 刚创建,无任何数据 → 返回空字符串"""
        asm, _, _ = _make_assembler(tmp_path)
        result = await asm.inject_graph_context(1, [])
        assert result == ""

    async def test_empty_result_for_first_chapters(self, tmp_path):
        """chapter_num <= 5 且无任何提醒时也不输出正向反馈"""
        asm, _, _ = _make_assembler(tmp_path)
        result = await asm.inject_graph_context(3, [])
        assert result == ""

    async def test_positive_feedback_after_chapter_5(self, tmp_path):
        """chapter_num > 5 且无任何提醒时给正向反馈"""
        asm, _, _ = _make_assembler(tmp_path)
        result = await asm.inject_graph_context(10, [])
        assert "图谱状态" in result
        assert "正常" in result

    async def test_long_absent_character_warning(self, tmp_path):
        """出场角色超过 5 章未出现 — 触发回归提醒"""
        asm, _, data_dir = _make_assembler(tmp_path)
        _write_char(data_dir, "林默", last_ch=3)
        # 当前章节 10, 林默出场, gap=7 > 5
        result = await asm.inject_graph_context(10, [CharacterCard(name="林默")])
        assert "角色回归提醒" in result
        assert "林默" in result
        assert "7 章" in result

    async def test_dead_character_not_warned(self, tmp_path):
        """死亡角色不出现在回归提醒里"""
        asm, _, data_dir = _make_assembler(tmp_path)
        _write_char(data_dir, "老王", last_ch=1, status="dead")
        result = await asm.inject_graph_context(20, [CharacterCard(name="老王")])
        assert "角色回归提醒" not in result
        assert "老王" not in result

    async def test_left_character_not_warned(self, tmp_path):
        """已离场角色不出现在回归提醒里"""
        asm, _, data_dir = _make_assembler(tmp_path)
        _write_char(data_dir, "李四", last_ch=1, status="left")
        result = await asm.inject_graph_context(20, [CharacterCard(name="李四")])
        assert "李四" not in result

    async def test_rarely_seen_character_warning(self, tmp_path):
        """未出场角色 — 触发剧情密度提醒(需要 > 2 个未出场角色)"""
        asm, _, data_dir = _make_assembler(tmp_path)
        _write_char(data_dir, "配角甲", last_ch=2)
        _write_char(data_dir, "配角乙", last_ch=3)
        _write_char(data_dir, "配角丙", last_ch=4)
        # 本章只有主角出场,3 个配角未出场
        result = await asm.inject_graph_context(20, [CharacterCard(name="主角")])
        assert "剧情密度" in result
        assert "配角甲" in result

    async def test_foreshadow_critical_age(self, tmp_path):
        """伏笔超过 critical 年龄(>40) — 紧急提醒"""
        asm, _, data_dir = _make_assembler(tmp_path)
        # 埋在第 1 章,当前第 50 章, age=49 > 40
        fs_data = [
            {"status": "planted", "planted_chapter": 1, "description": "神秘项链"},
        ]
        (data_dir / "foreshadows.json").write_text(
            json.dumps(fs_data, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(50, [])
        assert "伏笔紧急" in result
        assert "神秘项链" in result
        assert "49 章" in result

    async def test_foreshadow_normal_age(self, tmp_path):
        """伏笔 normal < age <= critical — 普通提醒"""
        asm, _, data_dir = _make_assembler(tmp_path)
        # 埋在第 1 章,当前第 30 章, age=29 (25 < 29 <= 40)
        fs_data = [
            {"status": "planted", "planted_chapter": 1, "description": "古老预言"},
        ]
        (data_dir / "foreshadows.json").write_text(
            json.dumps(fs_data, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(30, [])
        assert "伏笔提醒" in result
        assert "古老预言" in result
        assert "伏笔紧急" not in result

    async def test_foreshadow_young_no_warning(self, tmp_path):
        """伏笔年龄 <= normal — 不提醒(检查不含"伏笔紧急"或"伏笔提醒")"""
        asm, _, data_dir = _make_assembler(tmp_path)
        fs_data = [
            {"status": "planted", "planted_chapter": 1, "description": "小伏笔"},
        ]
        (data_dir / "foreshadows.json").write_text(
            json.dumps(fs_data, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(20, [])  # age=19 < 25
        assert "伏笔紧急" not in result
        assert "伏笔提醒" not in result

    async def test_foreshadow_resolved_skipped(self, tmp_path):
        """已回收的伏笔不再提醒"""
        asm, _, data_dir = _make_assembler(tmp_path)
        fs_data = [
            {"status": "resolved", "planted_chapter": 1, "description": "已解之谜"},
        ]
        (data_dir / "foreshadows.json").write_text(
            json.dumps(fs_data, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(50, [])
        assert "已解之谜" not in result

    async def test_foreshadow_planted_in_future_skipped(self, tmp_path):
        """埋在未来章节的伏笔不提醒"""
        asm, _, data_dir = _make_assembler(tmp_path)
        fs_data = [
            {"status": "planted", "planted_chapter": 100, "description": "未来伏笔"},
        ]
        (data_dir / "foreshadows.json").write_text(
            json.dumps(fs_data, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(50, [])
        assert "未来伏笔" not in result

    async def test_relationship_tension(self, tmp_path):
        """本章出场角色之间存在高强度负面关系 — 触发张力提示"""
        asm, _, data_dir = _make_assembler(tmp_path)
        rels = [
            {
                "source_name": "林默",
                "target_name": "黑衣人",
                "category": "negative",
                "intensity": 9,
                "rel_type": "仇敌",
                "description": "血海深仇",
            },
            {
                "source_name": "林默",
                "target_name": "路人甲",
                "category": "negative",
                "intensity": 3,  # 强度不足
                "rel_type": "不和",
                "description": "口角",
            },
        ]
        (data_dir / "relationships.json").write_text(
            json.dumps(rels, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(
            10, [CharacterCard(name="林默"), CharacterCard(name="黑衣人")]
        )
        assert "关系张力" in result
        assert "林默" in result
        assert "黑衣人" in result
        assert "血海深仇" in result
        # 低强度关系不应出现
        assert "口角" not in result

    async def test_relationship_no_tension_for_positive(self, tmp_path):
        """正面关系不触发张力提示"""
        asm, _, data_dir = _make_assembler(tmp_path)
        rels = [
            {
                "source_name": "林默",
                "target_name": "李老师",
                "category": "positive",
                "intensity": 9,
                "rel_type": "师生",
                "description": "良师益友",
            },
        ]
        (data_dir / "relationships.json").write_text(
            json.dumps(rels, ensure_ascii=False), encoding="utf-8"
        )
        result = await asm.inject_graph_context(
            10, [CharacterCard(name="林默"), CharacterCard(name="李老师")]
        )
        assert "关系张力" not in result

    async def test_malformed_json_skipped_gracefully(self, tmp_path):
        """损坏的 JSON 文件不抛异常,优雅降级"""
        asm, _, data_dir = _make_assembler(tmp_path)
        (data_dir / "foreshadows.json").write_text(
            "not a valid json {{{", encoding="utf-8"
        )
        (data_dir / "relationships.json").write_text(
            "also broken }}}", encoding="utf-8"
        )
        # 不抛异常即可
        result = await asm.inject_graph_context(10, [])
        # 仍然给正向反馈(无可用数据)
        assert "图谱状态" in result

    async def test_malformed_character_yaml_skipped(self, tmp_path):
        """损坏的角色卡 YAML 不抛异常"""
        asm, _, data_dir = _make_assembler(tmp_path)
        chars_dir = data_dir / "characters"
        chars_dir.mkdir(parents=True, exist_ok=True)
        (chars_dir / "坏角色.yaml").write_text(
            "name: [invalid, yaml, structure, {", encoding="utf-8"
        )
        # 不抛异常即可
        result = await asm.inject_graph_context(10, [])
        assert isinstance(result, str)
