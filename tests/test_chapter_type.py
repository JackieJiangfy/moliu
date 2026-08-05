"""测试章节类型路由功能 (Phase 1.5)"""

import pytest


class TestChapterTypeResolution:
    """测试章节类型解析（自动检测）"""

    def test_resolve_chapter_type_first_chapter(self, prompts, test_config, temp_dir):
        """测试第一章的类型解析"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 第一章 auto -> opening
        chapter_type = generator._resolve_chapter_type(1, "auto")
        assert chapter_type == "opening"
        
        # 第二章 auto -> setup
        chapter_type = generator._resolve_chapter_type(2, "auto")
        assert chapter_type == "setup"
        
        # 第三章 auto -> setup
        chapter_type = generator._resolve_chapter_type(3, "auto")
        assert chapter_type == "setup"

    def test_resolve_chapter_type_middle_chapters(self, prompts, test_config, temp_dir):
        """测试中间章节的类型解析"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 第四章及以后 auto -> normal
        for i in range(4, 20):
            chapter_type = generator._resolve_chapter_type(i, "auto")
            assert chapter_type == "normal", f"第{i}章应该是 normal"

    def test_resolve_chapter_type_manual_override(self, prompts, test_config, temp_dir):
        """测试手动指定章节类型"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 手动指定的类型应该保持不变
        assert generator._resolve_chapter_type(1, "climax") == "climax"
        assert generator._resolve_chapter_type(10, "epilogue") == "epilogue"
        assert generator._resolve_chapter_type(5, "transition") == "transition"

    def test_resolve_chapter_type_invalid(self, prompts, test_config, temp_dir):
        """测试无效章节类型回退"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 无效类型应该回退到 normal
        assert generator._resolve_chapter_type(5, "invalid_type") == "normal"
        assert generator._resolve_chapter_type(5, "") == "normal"


class TestChapterGuidance:
    """测试章节引导内容"""

    def test_get_chapter_guidance_opening(self, prompts, test_config, temp_dir):
        """测试开场章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("opening")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含开场相关的引导词
        assert "开场" in guidance
        assert "世界观" in guidance or "主角" in guidance

    def test_get_chapter_guidance_climax(self, prompts, test_config, temp_dir):
        """测试高潮章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("climax")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含高潮相关的引导词
        assert "高潮" in guidance
        assert "冲突" in guidance or "对决" in guidance

    def test_get_chapter_guidance_epilogue(self, prompts, test_config, temp_dir):
        """测试收尾章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("epilogue")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含收尾相关的引导词
        assert "收尾" in guidance or "结局" in guidance

    def test_get_chapter_guidance_transition(self, prompts, test_config, temp_dir):
        """测试过渡章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("transition")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含过渡相关的引导词
        assert "过渡" in guidance or "承上启下" in guidance

    def test_get_chapter_guidance_setup(self, prompts, test_config, temp_dir):
        """测试铺垫章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("setup")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含铺垫相关的引导词
        assert "铺垫" in guidance or "伏笔" in guidance

    def test_get_chapter_guidance_normal(self, prompts, test_config, temp_dir):
        """测试普通章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("normal")
        
        assert guidance is not None
        assert len(guidance) > 0
        # 应该包含普通章节相关的引导词
        assert "推进" in guidance or "主线" in guidance

    def test_get_chapter_guidance_invalid(self, prompts, test_config, temp_dir):
        """测试无效章节类型的引导（回退到 normal）"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        guidance = generator._get_chapter_guidance("invalid_type")
        
        assert guidance is not None
        assert "普通" in guidance or "推进" in guidance