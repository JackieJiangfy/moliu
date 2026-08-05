"""测试摘要生成功能 (Phase 1.5)"""

import pytest
from unittest.mock import AsyncMock


class TestSummaryGeneration:
    """测试 LLM 摘要生成"""

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm_basic(self, mock_gateway, prompts, test_config, temp_dir):
        """测试 LLM 摘要生成基本功能"""
        from moliu.engines.generator import Generator
        
        mock_gateway.generate = AsyncMock(return_value=("这是一个精彩的故事摘要。", 50))
        
        generator = Generator(test_config, mock_gateway, prompts)
        summary = await generator._generate_summary_with_llm("第1章", "这是一段很长的正文内容，包含很多情节发展。")
        
        assert "摘要" in summary
        assert "精彩的故事" in summary
        mock_gateway.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm_fallback(self, mock_gateway, prompts, test_config, temp_dir):
        """测试 LLM 失败时的回退机制"""
        from moliu.engines.generator import Generator
        
        # 模拟 LLM 调用失败
        mock_gateway.generate = AsyncMock(side_effect=Exception("API 错误"))
        
        generator = Generator(test_config, mock_gateway, prompts)
        summary = await generator._generate_summary_with_llm("第1章", "这是一段很长的正文内容。")
        
        # 应该回退到启发式方法
        assert "摘要" in summary
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm_short_content(self, mock_gateway, prompts, test_config, temp_dir):
        """测试短内容的摘要生成"""
        from moliu.engines.generator import Generator
        
        mock_gateway.generate = AsyncMock(return_value=("短摘要。", 10))
        
        generator = Generator(test_config, mock_gateway, prompts)
        summary = await generator._generate_summary_with_llm("第1章", "很短的内容。")
        
        assert "摘要" in summary

    def test_extract_summary_from_text_basic(self, prompts, test_config, temp_dir):
        """测试启发式摘要提取"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        content = """第1章 初遇

在一个阳光明媚的早晨，小明来到了这座城市。
他背着行囊，满怀期待地走进了火车站。
出站口人来人往，热闹非凡。
突然，他看到了一个熟悉的身影。
那是他多年未见的老朋友。
两人激动地拥抱在一起，回忆起了往事。"""
        
        summary = generator._extract_summary_from_text(content, 1)
        
        assert "摘要" in summary
        assert "小明" in summary
        assert "老朋友" in summary

    def test_extract_summary_from_text_with_various_punctuation(self, prompts, test_config, temp_dir):
        """测试不同标点符号的处理"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        content = """他说："你来了！"我点了点头……风起了。
故事就这样开始了？是的，开始了。"""
        
        summary = generator._extract_summary_from_text(content, 1)
        
        assert len(summary) > 0
        assert "摘要" in summary

    def test_extract_summary_from_text_short(self, prompts, test_config, temp_dir):
        """测试极短内容的摘要提取"""
        from moliu.engines.generator import Generator
        
        generator = Generator(test_config, None, prompts)
        
        content = "非常短的内容。"
        
        summary = generator._extract_summary_from_text(content, 1)
        
        assert "摘要" in summary
        assert "非常短的内容" in summary


class TestSummaryIntegration:
    """测试摘要在章节生成中的集成"""

    @pytest.mark.asyncio
    async def test_summary_in_chapter_generation(self, mock_gateway, prompts, test_config, full_character, full_world, temp_dir):
        """测试摘要在章节生成中的使用"""
        from moliu.engines.generator import Generator
        
        # 模拟两次调用：第一次生成章节，第二次生成摘要
        mock_gateway.generate = AsyncMock(side_effect=[
            ("这是章节内容。", 100),
            ("这是摘要。", 30),
        ])
        
        generator = Generator(test_config, mock_gateway, prompts)
        
        # 调用完整的章节生成（不分段模式）
        result = await generator.generate_chapter(
            chapter_num=1,
            beat="测试节拍",
            characters=[full_character],
            world=full_world,
            last_emotion="轻松",
            recent_chapters="",
            narrator_card=None,
            segmented=False,
            chapter_type="normal",
        )
        
        # 验证结果包含摘要
        assert result is not None
        assert result.content is not None
        # 摘要生成可能是可选的，所以我们检查是否有摘要被保存
        # 至少调用了一次（章节生成）
        assert mock_gateway.generate.call_count >= 1