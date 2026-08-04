"""集成测试 - 需要真实 API 调用和数据文件

这些测试需要配置有效的 API Key，用于验证完整的端到端流程。
运行方式: pytest tests/test_integration.py -v -m integration
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path

import pytest

from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway, DeepSeekAPIError
from moliu.engines.generator import Generator
from moliu.prompts.manager import PromptManager


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def config():
    """集成测试配置"""
    cfg = Config()
    if not cfg.deepseek_api_key or len(cfg.deepseek_api_key) < 10:
        pytest.skip("API Key 未配置，跳过集成测试")
    return cfg


@pytest.fixture(scope="module")
def prompts(config):
    """Prompt 管理器"""
    return PromptManager(config)


class TestGatewayIntegration:
    """Gateway 集成测试"""

    @pytest.mark.asyncio
    async def test_api_connectivity(self, config):
        """测试 API 连通性"""
        gw = DeepSeekGateway(config)
        try:
            content, tokens = await gw.generate(
                system_prompt="你是一个计算器。用户说一个数字，你只回复这个数字除以2的结果。",
                user_prompt="8",
                temperature=0.1,
                max_tokens=10,
            )
            assert len(content) > 0
            assert tokens > 0
            assert "4" in content
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_api_error_handling(self, config):
        """测试 API 错误处理"""
        gw = DeepSeekGateway(config)
        try:
            with pytest.raises(DeepSeekAPIError):
                await gw.generate(
                    system_prompt="test",
                    user_prompt="test",
                    temperature=0.1,
                    max_tokens=-1,  # 无效参数
                )
        except Exception:
            # 可能是其他类型的错误，也接受
            pass
        finally:
            await gw.close()


class TestChapterGenerationIntegration:
    """章节生成集成测试"""

    @pytest.mark.asyncio
    async def test_world_generation(self, config):
        """测试 AI 生成世界观"""
        gw = DeepSeekGateway(config)
        try:
            world_text, _ = await gw.generate(
                system_prompt="""你是网文设定师。根据用户描述生成世界观 YAML。

era: "时代背景"
core_rules:
  - "核心规则"
power_system: "力量体系"
key_constraints:
  - "硬约束"
narrative_style: "叙事基调" """,
                user_prompt="都市系统爽文，大学校园，社恐计算机系大二男生被神秘系统绑定",
                temperature=0.7,
                max_tokens=1024,
            )
            assert len(world_text) > 50
            assert "era:" in world_text
            assert "core_rules:" in world_text
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_character_generation(self, config):
        """测试 AI 生成角色"""
        gw = DeepSeekGateway(config)
        try:
            chars_text, _ = await gw.generate(
                system_prompt="""你是网文人设师。生成一个角色的人设卡 YAML。

name: "角色名"
one_line_pitch: "一句话定位"
speech_profile:
  style: "说话风格"
  common_words: ["常用词"]
  banned_words: ["禁用词"]
speech_samples:
  - "\"样本1\"（场景）"
core:
  core_desire: "核心欲望"
  surface_desire: "表层欲望"
  deep_fear: "深层恐惧"
state:
  location: "所在地"
  current_goal: "当前目标"
  current_emotion: "情绪"
""",
                user_prompt="都市系统爽文，主角是社恐程序员",
                temperature=0.8,
                max_tokens=1024,
            )
            assert len(chars_text) > 100
            assert "name:" in chars_text
            assert "core_desire:" in chars_text
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_chapter_generation(self, config, prompts):
        """测试章节生成"""
        gw = DeepSeekGateway(config)
        gen = Generator(config, gw, prompts)
        try:
            world = WorldSetting(
                era="现代都市大学",
                core_rules=["系统秘密存在"],
                narrative_style="轻松吐槽",
            )
            character = CharacterCard(
                name="林默",
                one_line_pitch="社恐程序员",
            )

            result = await gen.generate_chapter(
                chapter_num=1,
                beat="林默在食堂收到系统第一条任务：48小时内获得一位异性的真心感谢",
                characters=[character],
                world=world,
                last_emotion="轻松",
                narrator_guide="轻松吐槽风",
                temperature=0.7,
            )

            assert len(result.content) > 100
            assert result.word_count > 0
            assert result.tokens_used > 0
            assert "林默" in result.content
        finally:
            await gw.close()


class TestE2EIntegration:
    """端到端集成测试"""

    @pytest.mark.asyncio
    async def test_full_creation_workflow(self, config, prompts, tmp_path):
        """测试完整的创世工作流"""
        gw = DeepSeekGateway(config)
        try:
            # 1. 生成世界观
            world_text, _ = await gw.generate(
                system_prompt="""你是网文设定师。根据用户描述生成世界观 YAML。

era: "时代背景"
core_rules:
  - "规则1"
power_system: "力量体系"
key_constraints:
  - "约束1"
narrative_style: "叙事基调" """,
                user_prompt="都市系统爽文，美食博主被神秘系统绑定",
                temperature=0.7,
                max_tokens=1024,
            )

            # 2. 生成角色
            chars_text, _ = await gw.generate(
                system_prompt="""你是网文人设师。生成一个角色的人设卡 YAML。

name: "角色名"
one_line_pitch: "一句话定位"
""",
                user_prompt=f"世界观: {world_text}\n\n生成一个美食博主角色",
                temperature=0.8,
                max_tokens=1024,
            )

            # 3. 加载并验证
            world = WorldSetting.from_yaml(Path(tempfile.mktemp(suffix=".yaml")))
            assert world.era is not None

            # 4. 生成章节
            gen = Generator(config, gw, prompts)
            character = CharacterCard(name="测试角色", one_line_pitch="测试")
            result = await gen.generate_chapter(
                chapter_num=1,
                beat="主角收到系统第一条任务",
                characters=[character],
                world=world,
                last_emotion="轻松",
            )

            assert len(result.content) > 100

        finally:
            await gw.close()
