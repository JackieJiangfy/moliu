"""Prompt 模板单元测试"""

import pytest

from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.prompts.manager import PromptManager


class TestPromptManager:
    """Prompt 模板管理器测试"""

    def test_prompt_manager_init(self):
        """PromptManager 初始化"""
        config = Config()
        prompts = PromptManager(config)
        assert prompts is not None

    def test_render_chapter_system(self):
        """渲染章节生成系统 Prompt"""
        config = Config()
        prompts = PromptManager(config)

        world = WorldSetting(
            era="现代都市大学",
            core_rules=["系统秘密存在"],
            narrative_style="轻松吐槽",
        )
        character = CharacterCard(
            name="林默",
            one_line_pitch="测试角色",
        )

        sys_p = prompts.render(
            "chapter_generate.system.j2",
            world_setting=world.to_context(),
            narrator_card="",
            narrator_guide="叙述者: 轻松吐槽风",
            character_context=character.to_context(),
            banned_phrases=[],
            min_words=1800,
            max_words=3500,
            chapter_guidance="",
        )

        assert "现代都市大学" in sys_p
        assert "林默" in sys_p
        assert "1800" in sys_p
        assert "轻松吐槽风" in sys_p
        assert "写作要求" in sys_p

    def test_render_chapter_user(self):
        """渲染章节生成用户 Prompt"""
        config = Config()
        prompts = PromptManager(config)

        usr_p = prompts.render(
            "chapter_generate.user.j2",
            chapter_num=1,
            beat="林默在食堂收到系统第一条任务",
            last_emotion="轻松",
            recent_chapters="",
        )

        assert "第 1 章" in usr_p
        assert "林默在食堂收到系统第一条任务" in usr_p
        assert "轻松" in usr_p
        assert "写作任务" in usr_p

    def test_render_with_recent_chapters(self):
        """渲染包含前文回顾的 Prompt"""
        config = Config()
        prompts = PromptManager(config)

        usr_p = prompts.render(
            "chapter_generate.user.j2",
            chapter_num=2,
            beat="第二章节拍",
            last_emotion="紧张",
            recent_chapters="第一章：林默获得了系统。",
        )

        assert "前文章节回顾" in usr_p
        assert "林默获得了系统" in usr_p

    def test_render_missing_template(self):
        """渲染不存在的模板"""
        config = Config()
        prompts = PromptManager(config)

        with pytest.raises(Exception):
            prompts.render("nonexistent_template.j2", test="value")

    def test_system_user_separation(self):
        """System 和 User Prompt 内容分离"""
        config = Config()
        prompts = PromptManager(config)

        sys_p = prompts.render(
            "chapter_generate.system.j2",
            world_setting="测试",
            narrator_card="",
            narrator_guide="测试",
            character_context="测试",
            banned_phrases=[],
            min_words=1800,
            max_words=3500,
            chapter_guidance="",
        )
        usr_p = prompts.render(
            "chapter_generate.user.j2",
            chapter_num=1,
            beat="测试",
            last_emotion="轻松",
            recent_chapters="",
        )

        assert "写作要求" in sys_p
        assert "写作任务" not in sys_p
        assert "写作任务" in usr_p
        assert "写作要求" not in usr_p
