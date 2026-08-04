"""Schema 单元测试 - 角色卡、世界观、序列化"""

import os
import tempfile
from pathlib import Path

import pytest

from moliu.data.schemas import (
    Appearance,
    CharacterCard,
    CharacterCore,
    CharacterState,
    SpeechProfile,
    WorldSetting,
)


class TestCharacterCard:
    """角色卡 Schema 测试"""

    def test_empty_character(self):
        """空角色卡不崩溃"""
        empty = CharacterCard(name="X")
        ctx = empty.to_context()
        assert len(ctx) >= 0
        assert "。。" not in ctx
        assert "说话风格:" not in ctx

    def test_full_character(self):
        """完整角色卡 to_context"""
        full = CharacterCard(
            name="林默",
            one_line_pitch="社恐程序员被系统逼成校园风云人物",
            speech_profile=SpeechProfile(
                style="简短理性",
                sentence_length="短句为主",
                tone="陈述多，感叹号少",
                common_words=["行", "嗯", "懂了"],
                banned_words=["真的吗", "太好了", "天啊"],
            ),
            speech_samples=[
                '"行。"（被要求做任务时）',
                '"分析过了。三个方案，第一种最快。"（遇到问题时）',
            ],
            inner_voice_style="代码注释式——'// 苏晚晴又来了。第三次。概率不正常。'",
            core=CharacterCore(
                core_desire="掌控自己的人生",
                surface_desire="完成系统任务，变强",
                deep_fear="再次失去在乎的人",
                value_bottom_line=["不伤及无辜", "不用系统能力违法"],
            ),
            backstory_summary="8岁父母车祸去世，被姨妈养大",
            backstory_impact="安全感缺失→追求确定性→选计算机专业",
            state=CharacterState(
                location="A市大学城3号宿舍楼512",
                current_goal="完成系统第5个任务",
                current_emotion="紧张但冷静",
            ),
            appearance=Appearance(
                height="178cm",
                build="偏瘦",
                face="清秀不突出，黑框眼镜",
                hair="黑色短发，不造型",
                typical_outfit="深色卫衣/帽衫+牛仔裤",
                signature_gesture="想事情时扶眼镜",
            ),
        )
        ctx_full = full.to_context()
        assert "林默" in ctx_full
        assert '"行。"' in ctx_full
        assert "真的吗" in ctx_full
        assert "掌控自己的人生" in ctx_full
        assert "代码注释式" in ctx_full

    def test_yaml_roundtrip(self):
        """YAML 读写往返"""
        full = CharacterCard(
            name="林默",
            one_line_pitch="测试角色",
            speech_profile=SpeechProfile(
                style="简短理性",
                common_words=["行", "嗯"],
                banned_words=["真的吗"],
            ),
            speech_samples=['"行。"（被要求做任务时）'],
        )
        tmp = tempfile.mktemp(suffix=".yaml")
        try:
            full.to_yaml(tmp)
            loaded = CharacterCard.from_yaml(tmp)
            assert loaded.name == full.name
            assert loaded.speech_samples == full.speech_samples
            assert loaded.one_line_pitch == full.one_line_pitch
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_from_yaml_invalid_path(self):
        """from_yaml 处理不存在的文件"""
        with pytest.raises(FileNotFoundError):
            CharacterCard.from_yaml(Path("/nonexistent/char.yaml"))

    def test_from_yaml_invalid_content(self):
        """from_yaml 处理无效 YAML"""
        tmp = tempfile.mktemp(suffix=".yaml")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("not a dict: invalid")
            with pytest.raises(Exception):
                CharacterCard.from_yaml(tmp)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_character_core_no_redundant_field(self):
        """CharacterCore 无冗余字段"""
        assert "one_line_pitch" not in CharacterCore.model_fields


class TestWorldSetting:
    """世界观 Schema 测试"""

    def test_empty_world(self):
        """空世界观不崩溃"""
        ws_empty = WorldSetting()
        ctx = ws_empty.to_context()
        assert len(ctx) >= 0
        assert "时代:" not in ctx

    def test_full_world(self):
        """完整世界观 to_context"""
        ws_full = WorldSetting(
            era="现代都市大学",
            core_rules=["系统秘密存在", "能力与现实法则共存"],
            power_system="等级制 F/E/D/C/B/A/S",
            faction_summary="系统拥有者协会 + 普通人类社会",
            key_constraints=["不能直接杀人", "能力不能直接变现"],
            narrative_style="轻松吐槽，快节奏爽文",
        )
        ctx = ws_full.to_context()
        assert "现代都市大学" in ctx
        assert "系统秘密存在" in ctx
        assert "不能直接杀人" in ctx

    def test_yaml_roundtrip(self):
        """YAML 读写往返"""
        ws = WorldSetting(
            era="现代都市大学",
            core_rules=["规则1", "规则2"],
            narrative_style="轻松吐槽",
        )
        tmp = tempfile.mktemp(suffix=".yaml")
        try:
            import yaml

            with open(tmp, "w", encoding="utf-8") as f:
                yaml.dump(
                    ws.model_dump(),
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                )
            loaded = WorldSetting.from_yaml(tmp)
            assert loaded.era == ws.era
            assert loaded.core_rules == ws.core_rules
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_to_context_format(self):
        """to_context 输出格式正确"""
        ws = WorldSetting(era="测试时代")
        ctx = ws.to_context()
        assert "【世界观】" in ctx
        assert "时代: 测试时代" in ctx
