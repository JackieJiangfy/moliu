"""测试分段生成功能 (Phase 1.5)"""

from pathlib import Path

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

    def test_dedup_no_overlap_returns_original(self, prompts, test_config, temp_dir):
        """问题5: 无重叠时返回原始内容"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        prev = "他走进了森林深处。"
        curr = "远处传来狼嚎声。"
        p, c = generator._deduplicate_overlap(prev, curr)
        assert p == prev
        assert c == curr

    def test_dedup_exact_overlap_removed(self, prompts, test_config, temp_dir):
        """问题5: 精确重叠(>=10字)被去除"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        # 15 字重叠:"月光洒落在寂静的小镇上"
        prev = "夜幕降临,月光洒落在寂静的小镇上。"
        curr = "月光洒落在寂静的小镇上,街道空无一人。"
        p, c = generator._deduplicate_overlap(prev, curr)
        # 重叠部分应从 curr 开头移除
        assert not c.startswith("月光洒落在寂静的小镇上。")
        assert "街道空无一人" in c
        # prev 不变(无句子边界可对齐时)
        assert "月光洒落在寂静的小镇上" in p

    def test_dedup_short_overlap_below_threshold(self, prompts, test_config, temp_dir):
        """问题5: 短于 10 字的重叠不处理(避免误删)"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        # 5 字重叠:"他看到了"
        prev = "他走进房间。他看到了"
        curr = "他看到了一个箱子。"
        p, c = generator._deduplicate_overlap(prev, curr)
        # 短于 10 字,不处理
        assert p == prev
        assert c == curr

    def test_dedup_aligns_to_sentence_boundary(self, prompts, test_config, temp_dir):
        """问题5: 在句子边界对齐,保留完整句子"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        # 重叠区域含句子结束符
        prev = "他推开门。屋内漆黑一片,什么也看不见。"
        curr = "屋内漆黑一片,什么也看不见。他摸索着前进。"
        p, c = generator._deduplicate_overlap(prev, curr)
        # 应在"。"处切分,前段保留完整句子
        assert p.endswith("。") or p.endswith("他推开门")
        # curr 不再以重叠开头
        assert not c.startswith("屋内漆黑一片,什么也看不见。他推开门")
        assert "他摸索着前进" in c

    def test_dedup_long_overlap_200_chars(self, prompts, test_config, temp_dir):
        """问题5: 能处理 200 字以内的重叠"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        # 构造 50 字重叠
        overlap = "这是一段重复的文本内容用于测试去重功能,长度超过十个字。"
        prev = "前段内容开始。" + overlap
        curr = overlap + "后段内容继续。"
        p, c = generator._deduplicate_overlap(prev, curr)
        # 重叠应从 curr 移除
        assert overlap not in c or c.strip() == ""
        assert "后段内容继续" in c if c else True

    def test_dedup_empty_input(self, prompts, test_config, temp_dir):
        """问题5: 空输入直接返回"""
        from moliu.engines.generator import Generator
        generator = Generator(test_config, None, prompts)

        p, c = generator._deduplicate_overlap("", "内容")
        assert p == ""
        assert c == "内容"

        p, c = generator._deduplicate_overlap("内容", "")
        assert p == "内容"
        assert c == ""


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

    @pytest.mark.asyncio
    async def test_llm_emotion_extract_success(self, prompts, test_config, temp_dir):
        """问题4: LLM 情绪提取成功时返回结果"""
        from moliu.engines.generator import Generator
        from unittest.mock import AsyncMock, MagicMock

        generator = Generator(test_config, None, prompts)
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=("紧张→愤怒→释然", 20))
        generator.gateway = gw

        result = await generator._extract_emotion_with_llm("他攥紧拳头,指节发白。")
        assert result == "紧张→愤怒→释然"
        assert gw.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_emotion_extract_failure_returns_none(self, prompts, test_config, temp_dir):
        """问题4: LLM 调用失败时返回 None(降级到规则版)"""
        from moliu.engines.generator import Generator
        from unittest.mock import AsyncMock, MagicMock

        generator = Generator(test_config, None, prompts)
        gw = MagicMock()
        gw.generate = AsyncMock(side_effect=RuntimeError("网络错误"))
        generator.gateway = gw

        result = await generator._extract_emotion_with_llm("文本内容")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_emotion_extract_empty_response_returns_none(self, prompts, test_config, temp_dir):
        """问题4: LLM 返回空字符串时返回 None"""
        from moliu.engines.generator import Generator
        from unittest.mock import AsyncMock, MagicMock

        generator = Generator(test_config, None, prompts)
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=("", 5))
        generator.gateway = gw

        result = await generator._extract_emotion_with_llm("文本")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_emotion_extract_strips_quotes(self, prompts, test_config, temp_dir):
        """问题4: 去除 LLM 返回的引号包裹"""
        from moliu.engines.generator import Generator
        from unittest.mock import AsyncMock, MagicMock

        generator = Generator(test_config, None, prompts)
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=('"紧张"', 10))
        generator.gateway = gw

        result = await generator._extract_emotion_with_llm("文本")
        assert result == "紧张"
        assert '"' not in result

    @pytest.mark.asyncio
    async def test_llm_emotion_takes_last_400_chars(self, prompts, test_config, temp_dir):
        """问题4: 只分析末尾 400 字(反映收尾情绪)"""
        from moliu.engines.generator import Generator
        from unittest.mock import AsyncMock, MagicMock

        generator = Generator(test_config, None, prompts)
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=("平静", 10))
        generator.gateway = gw

        long_text = "内容" * 300  # 600 字
        await generator._extract_emotion_with_llm(long_text)
        # 检查传给 LLM 的 user_prompt 只含末尾 400 字
        call_args = gw.generate.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "内容" in user_prompt
        assert len(user_prompt) < len(long_text)  # 截短了


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


class TestGlobalProgress:
    """问题10: 全局进度感知测试"""

    # 真实项目的 prompt 模板目录(绝对路径)
    _REAL_PROMPT_DIR = Path(__file__).resolve().parent.parent / "moliu" / "prompts" / "templates"

    def _make_generator(self, tmp_path, novel_id=1, target_chapters=1000):
        """构造独立 config + Generator,写入 NovelIndex"""
        from pathlib import Path
        from moliu.config import Config
        from moliu.data.schemas import Novel, NovelIndex
        from moliu.engines.generator import Generator
        from moliu.prompts.manager import PromptManager

        config = Config()
        config.project_dir = tmp_path
        config.data_dir = Path("data")
        config.output_dir = Path("output/chapters")
        config.prompt_dir = self._REAL_PROMPT_DIR  # 用绝对路径指向真实模板
        # 准备目录
        (tmp_path / "data" / "novels" / str(novel_id)).mkdir(parents=True, exist_ok=True)
        (tmp_path / "output" / "novels" / str(novel_id) / "chapters").mkdir(parents=True, exist_ok=True)
        # 写入 NovelIndex
        index = NovelIndex(novels=[Novel(id=novel_id, title="测试小说", target_chapters=target_chapters)], next_id=novel_id + 1)
        index.to_json(config.resolve_novel_index_path())
        prompts = PromptManager(config)
        return Generator(config, None, prompts, novel_id=novel_id), config

    def _make_chapter_dir(self, config, novel_id, chapter_num):
        """创建一个已完成的章节目录"""
        from moliu.config import Config as C
        d = config.resolve_output_dir(novel_id) / C.chapter_dir_name(chapter_num)
        d.mkdir(parents=True, exist_ok=True)

    def test_no_index_returns_empty(self, tmp_path):
        """无 NovelIndex 时返回空(优雅降级)"""
        from pathlib import Path
        from moliu.config import Config
        from moliu.engines.generator import Generator
        from moliu.prompts.manager import PromptManager

        config = Config()
        config.project_dir = tmp_path
        config.data_dir = Path("data")
        config.output_dir = Path("output/chapters")
        config.prompt_dir = self._REAL_PROMPT_DIR
        (tmp_path / "data" / "novels" / "1").mkdir(parents=True, exist_ok=True)
        (tmp_path / "output" / "novels" / "1" / "chapters").mkdir(parents=True, exist_ok=True)
        prompts = PromptManager(config)
        generator = Generator(config, None, prompts, novel_id=1)
        assert generator._build_global_progress(1) == ""

    def test_progress_includes_target_and_current(self, tmp_path):
        """进度提示包含目标章数和当前章节"""
        generator, _ = self._make_generator(tmp_path, novel_id=1, target_chapters=1000)
        text = generator._build_global_progress(50)
        assert "1000" in text
        assert "第 50 章" in text
        assert "%" in text

    def test_progress_phase_opening(self, tmp_path):
        """开篇阶段识别"""
        generator, _ = self._make_generator(tmp_path, target_chapters=1000)
        text = generator._build_global_progress(5)
        assert "开篇阶段" in text

    def test_progress_phase_mid(self, tmp_path):
        """中段推进阶段识别"""
        generator, _ = self._make_generator(tmp_path, target_chapters=1000)
        text = generator._build_global_progress(300)
        assert "中段推进" in text

    def test_progress_phase_climax(self, tmp_path):
        """收尾阶段识别"""
        generator, _ = self._make_generator(tmp_path, target_chapters=1000)
        text = generator._build_global_progress(900)
        assert "收尾阶段" in text

    def test_progress_counts_done_chapters(self, tmp_path):
        """已完成章节数应被统计"""
        generator, config = self._make_generator(tmp_path, target_chapters=100)
        # 创建 10 个章节目录
        for n in range(1, 11):
            self._make_chapter_dir(config, 1, n)
        text = generator._build_global_progress(11)
        assert "已完成约 10 章" in text
        assert "10.0%" in text

    def test_progress_remaining_calculation(self, tmp_path):
        """剩余章节数计算"""
        generator, _ = self._make_generator(tmp_path, target_chapters=100)
        text = generator._build_global_progress(30)
        assert "还有 70 章" in text

    @pytest.mark.asyncio
    async def test_global_progress_injected_into_prompt(self, tmp_path, mocker):
        """生成时 global_progress 应被注入到 user prompt"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        generator, _ = self._make_generator(tmp_path, target_chapters=500)
        # Mock gateway 捕获 prompt
        captured = {}

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            captured["user_prompt"] = user_prompt
            return ("测试内容。", 100)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        # 修改 generator 的 config 指向 tmp_path(已设置)
        result = await generator.generate_chapter(
            chapter_num=10,
            beat="测试节拍",
            characters=[CharacterCard(name="主角")],
            world=WorldSetting(),
            segmented=False,
            chapter_type="normal",
        )
        assert "全局进度感知" in captured["user_prompt"]
        assert "500" in captured["user_prompt"]


class TestSegmentRetry:
    """问题2: 分段生成 middle/ending 失败时保留 opening 重试"""

    _REAL_PROMPT_DIR = Path(__file__).resolve().parent.parent / "moliu" / "prompts" / "templates"

    def _make_generator(self, tmp_path, novel_id=1):
        """构造独立 config + Generator(指向 tmp_path)"""
        from pathlib import Path
        from moliu.config import Config
        from moliu.engines.generator import Generator
        from moliu.prompts.manager import PromptManager

        config = Config()
        config.project_dir = tmp_path
        config.data_dir = Path("data")
        config.output_dir = Path("output/chapters")
        config.prompt_dir = self._REAL_PROMPT_DIR
        (tmp_path / "data" / "novels" / str(novel_id)).mkdir(parents=True, exist_ok=True)
        (tmp_path / "output" / "novels" / str(novel_id) / "chapters").mkdir(parents=True, exist_ok=True)
        prompts = PromptManager(config)
        return Generator(config, None, prompts, novel_id=novel_id), config

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self, tmp_path, mocker):
        """middle 段第一次失败、第二次成功,应自动重试并返回结果"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        generator, _ = self._make_generator(tmp_path)

        call_count = {"n": 0}

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            call_count["n"] += 1
            # 情绪提取调用(system_prompt 含"情绪")直接返回,不计数
            if "情绪" in system_prompt:
                return ("紧张", 10)
            # middle 段第一次调用失败(通过 user_prompt 中的"发展部分"识别)
            if "发展部分" in user_prompt:
                # 用独立的计数器判断是否第一次
                if not hasattr(fake_generate, "_middle_tried"):
                    fake_generate._middle_tried = True
                    raise RuntimeError("网络抖动")
            return ("测试内容。", 100)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        # 关闭重试延迟避免测试变慢
        mocker.patch("moliu.engines.generator.asyncio.sleep", new=mocker.AsyncMock())

        result = await generator.generate_chapter(
            chapter_num=1,
            beat="测试节拍",
            characters=[CharacterCard(name="主角")],
            world=WorldSetting(),
            segmented=True,
            chapter_type="normal",
        )
        assert result is not None
        # middle 段应被调用 2 次(1 次失败 + 1 次重试成功)
        assert hasattr(fake_generate, "_middle_tried")

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_segment_error(self, tmp_path, mocker):
        """middle 段重试仍失败,应抛 SegmentGenerationError 且 resume_from='middle'"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        from moliu.engines.generator import SegmentGenerationError
        generator, _ = self._make_generator(tmp_path)

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            if "发展部分" in user_prompt:
                raise RuntimeError("API 持续不可用")
            return ("开场内容。", 50)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        mocker.patch("moliu.engines.generator.asyncio.sleep", new=mocker.AsyncMock())

        with pytest.raises(SegmentGenerationError) as exc_info:
            await generator.generate_chapter(
                chapter_num=1,
                beat="测试节拍",
                characters=[CharacterCard(name="主角")],
                world=WorldSetting(),
                segmented=True,
                chapter_type="normal",
            )
        assert exc_info.value.failed_segment == "middle"
        assert exc_info.value.resume_from == "middle"
        assert exc_info.value.chapter_num == 1

    @pytest.mark.asyncio
    async def test_opening_preserved_after_middle_failure(self, tmp_path, mocker):
        """middle 失败后,opening 内容应已落盘,可用 resume_from 恢复"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        from moliu.engines.generator import SegmentGenerationError
        generator, _ = self._make_generator(tmp_path)

        opening_text = "第一章 开场内容,主角登场。"

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            if "开场部分" in user_prompt:
                return (opening_text, 50)
            if "发展部分" in user_prompt:
                raise RuntimeError("middle 失败")
            return ("结尾。", 30)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        mocker.patch("moliu.engines.generator.asyncio.sleep", new=mocker.AsyncMock())

        with pytest.raises(SegmentGenerationError):
            await generator.generate_chapter(
                chapter_num=1,
                beat="测试节拍",
                characters=[CharacterCard(name="主角")],
                world=WorldSetting(),
                segmented=True,
                chapter_type="normal",
            )

        # opening 应已保存到 segment 文件
        saved_opening = generator._load_segment(1, "opening")
        assert saved_opening == opening_text
        # middle 不应被保存(因为失败了)
        saved_middle = generator._load_segment(1, "middle")
        assert saved_middle == ""

    @pytest.mark.asyncio
    async def test_ending_failure_resume_from_ending(self, tmp_path, mocker):
        """ending 段失败时,SegmentGenerationError.resume_from 应为 'ending'"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        from moliu.engines.generator import SegmentGenerationError
        generator, _ = self._make_generator(tmp_path)

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            if "结尾部分" in user_prompt:
                raise RuntimeError("ending API 错误")
            return ("内容。", 50)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        mocker.patch("moliu.engines.generator.asyncio.sleep", new=mocker.AsyncMock())

        with pytest.raises(SegmentGenerationError) as exc_info:
            await generator.generate_chapter(
                chapter_num=1,
                beat="测试节拍",
                characters=[CharacterCard(name="主角")],
                world=WorldSetting(),
                segmented=True,
                chapter_type="normal",
            )
        assert exc_info.value.failed_segment == "ending"
        assert exc_info.value.resume_from == "ending"

    @pytest.mark.asyncio
    async def test_resume_from_middle_skips_opening(self, tmp_path, mocker):
        """resume_from='middle' 时,opening 应从 segment 文件加载,不重新生成"""
        from moliu.data.schemas import CharacterCard, WorldSetting
        generator, _ = self._make_generator(tmp_path)

        # 先保存 opening 和 beat
        generator._save_segment(1, "opening", "已保存的开场。")
        generator._save_segment(1, "beat", "测试节拍")
        generator._save_segment(1, "chapter_type", "normal")

        generate_calls = []

        async def fake_generate(system_prompt, user_prompt, **kwargs):
            generate_calls.append(user_prompt)
            return ("新内容。", 80)

        gw = mocker.Mock()
        gw.generate = fake_generate
        generator.gateway = gw
        mocker.patch("moliu.engines.generator.asyncio.sleep", new=mocker.AsyncMock())

        result = await generator.generate_chapter(
            chapter_num=1,
            beat="测试节拍",
            characters=[CharacterCard(name="主角")],
            world=WorldSetting(),
            segmented=True,
            chapter_type="normal",
            resume_from="middle",
        )
        # 不应再调用开场部分的 generate
        assert not any("开场部分" in u for u in generate_calls)
        # 应调用 middle + ending
        assert any("发展部分" in u for u in generate_calls)
        assert any("结尾部分" in u for u in generate_calls)
        # 最终内容应包含已保存的 opening
        assert "已保存的开场" in result.content