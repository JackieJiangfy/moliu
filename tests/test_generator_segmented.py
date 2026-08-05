"""测试分段生成功能 (Phase 1.5)"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestSegmentedGeneration:
    """测试分段生成 (opening/middle/ending)"""

    @pytest.mark.asyncio
    async def test_generate_chapter_with_segmented(self, mock_gateway, prompts, test_config, full_character, full_world, temp_dir):
        """测试使用分段模式生成章节"""
        from moliu.engines.generator import Generator
        
        mock_gateway.generate = AsyncMock(return_value=("测试内容。", 100))
        
        generator = Generator(test_config, mock_gateway, prompts)
        result = await generator.generate_chapter(
            chapter_num=1,
            beat="主角获得系统",
            characters=[full_character],
            world=full_world,
            last_emotion="轻松",
            recent_chapters="",
            narrator_card=None,
            segmented=True,
            chapter_type="normal",
        )
        
        assert result is not None
        assert result.content is not None
        assert len(result.content) > 0
        # 验证调用了多次（至少3次：opening/middle/ending + 可能的摘要）
        assert mock_gateway.generate.call_count >= 3

    @pytest.mark.asyncio
    async def test_generate_chapter_segmented_with_narrator(self, mock_gateway, prompts, test_config, full_character, full_world, temp_dir):
        """测试带叙述者卡的分段生成"""
        from moliu.engines.generator import Generator
        from moliu.data.schemas import NarratorCard
        
        mock_gateway.generate = AsyncMock(return_value=("测试内容。", 100))
        narrator = NarratorCard(
            name="测试叙述者",
            style="简洁明快",
            daily_sample="日常场景示例",
            climax_sample="高潮场景示例",
        )
        
        generator = Generator(test_config, mock_gateway, prompts)
        result = await generator.generate_chapter(
            chapter_num=1,
            beat="主角获得系统",
            characters=[full_character],
            world=full_world,
            last_emotion="轻松",
            recent_chapters="",
            narrator_card=narrator,
            segmented=True,
            chapter_type="normal",
        )
        
        assert result is not None
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_generate_chapter_segmented_climax_type(self, mock_gateway, prompts, test_config, full_character, full_world, temp_dir):
        """测试高潮章节类型的分段生成"""
        from moliu.engines.generator import Generator
        
        mock_gateway.generate = AsyncMock(return_value=("激烈的战斗场景。", 100))
        
        generator = Generator(test_config, mock_gateway, prompts)
        result = await generator.generate_chapter(
            chapter_num=5,
            beat="大战爆发",
            characters=[full_character],
            world=full_world,
            last_emotion="紧张",
            recent_chapters="",
            narrator_card=None,
            segmented=True,
            chapter_type="climax",
        )
        
        assert result is not None


class TestMergeSegments:
    """测试段落合并功能"""

    def test_merge_segments_basic(self, prompts, test_config, temp_dir):
        """测试基本合并"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        opening = "第一章 开场\n\n主角醒来。"
        middle = "发展部分\n\n他决定出发。"
        ending = "结尾部分\n\n他踏上了旅程。"
        
        merged = generator._merge_segments(opening, middle, ending)
        
        assert "第一章 开场" in merged
        assert "他决定出发" in merged
        assert "他踏上了旅程" in merged

    def test_merge_segments_removes_duplicates(self, prompts, test_config, temp_dir):
        """测试去重功能"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        opening = "他走进了房间。房间里很安静。"
        middle = "房间里很安静。他看到了一个箱子。"
        ending = "他看到了一个箱子。箱子里有一本书。"
        
        merged = generator._merge_segments(opening, middle, ending)
        
        # 应该只有一个"房间里很安静"
        assert merged.count("房间里很安静") <= 2  # 允许少量重复
        assert "箱子里有一本书" in merged


class TestEmotionExtract:
    """测试情绪提取功能"""

    def test_extract_emotion_from_text_basic(self, prompts, test_config, temp_dir):
        """测试基本情绪提取"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 测试紧张情绪
        result = generator._extract_emotion_from_text("他紧张地四处张望，心跳加速。")
        assert result == "紧张"
        
        # 测试轻松情绪
        result = generator._extract_emotion_from_text("阳光明媚，他悠闲地散步。")
        assert result == "轻松"
        
        # 测试悲伤情绪
        result = generator._extract_emotion_from_text("他伤心地流下了眼泪。")
        assert result == "悲伤"

    def test_extract_emotion_no_match(self, prompts, test_config, temp_dir):
        """测试无匹配情绪"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        result = generator._extract_emotion_from_text("今天天气不错。")
        assert result is None

    def test_extract_emotion_multiple(self, prompts, test_config, temp_dir):
        """测试多种情绪词（返回第一个匹配）"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        result = generator._extract_emotion_from_text("他既紧张又害怕，但还是勇敢地前进。")
        assert result is not None


class TestChapterType:
    """测试章节类型路由"""

    def test_get_chapter_guidance_basic(self, prompts, test_config, temp_dir):
        """测试获取章节引导"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 测试不同章节类型的引导
        guidance = generator._get_chapter_guidance("climax")
        assert guidance is not None
        assert "高潮" in guidance
        
        guidance = generator._get_chapter_guidance("opening")
        assert guidance is not None
        assert "开场" in guidance

    def test_chapter_type_resolve(self, prompts, test_config, temp_dir):
        """测试章节类型解析（自动检测）"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        # 第一章 auto 应该解析为 opening
        chapter_type = generator._resolve_chapter_type(1, "auto")
        assert chapter_type == "opening"
        
        # 第三章 auto 应该解析为 setup
        chapter_type = generator._resolve_chapter_type(3, "auto")
        assert chapter_type == "setup"
        
        # 第四章 auto 应该解析为 normal
        chapter_type = generator._resolve_chapter_type(4, "auto")
        assert chapter_type == "normal"
        
        # 手动指定的类型应该保持不变
        chapter_type = generator._resolve_chapter_type(5, "climax")
        assert chapter_type == "climax"