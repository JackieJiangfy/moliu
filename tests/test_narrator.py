"""NarratorCard 单元测试"""

import os
import tempfile
from pathlib import Path

import pytest

from moliu.data.schemas import NarratorCard


class TestNarratorCard:
    """叙述者人设卡测试"""

    def test_empty_narrator(self):
        """空叙述者卡不崩溃"""
        narrator = NarratorCard()
        ctx = narrator.to_context()
        assert len(ctx) >= 0
        assert "【叙述者】" in ctx  # 默认名字是"叙述者"

    def test_full_narrator(self):
        """完整叙述者卡 to_context"""
        narrator = NarratorCard(
            name="月老一号",
            one_line_pitch="一个以为自己只是工具的AI，最后比创造它的人更懂爱",
            daily_tone="轻松吐槽风，带点冷幽默",
            climax_tone="紧张刺激，节奏加快，短句为主",
            emotional_tone="温暖细腻，注重细节描写",
            sentence_features=[
                "用具体动作代替抽象情绪",
                "用食物/代码做比喻",
                "对话不预告，直接切",
            ],
            banned_phrases=[
                "他嘴角勾起一抹冷笑",
                "她心里涌过一阵暖流",
                "他的眼神深邃得像个漩涡",
            ],
            samples_daily="系统又弹任务了。这次是'今晚八点，去楼下便利店买一盒草莓味的创可贴'。",
            perspective="全知视角，双声道",
            language_style="现代口语化，带点网络流行语",
        )
        ctx = narrator.to_context()
        assert "【月老一号】" in ctx  # 现在用名字作为标题
        assert "定位:" in ctx
        assert "一个以为自己只是工具的AI" in ctx
        assert "轻松吐槽风" in ctx
        assert "用具体动作代替抽象情绪" in ctx
        assert "他嘴角勾起一抹冷笑" in ctx
        assert "系统又弹任务了" in ctx

    def test_narrator_with_banned_phrases(self):
        """叙述者卡包含禁用套话"""
        narrator = NarratorCard(
            banned_phrases=[
                "心中涌起暖流",
                "眼中闪过一丝",
                "不由得",
            ]
        )
        ctx = narrator.to_context()
        assert "禁用套话:" in ctx
        assert "心中涌起暖流" in ctx
        assert "眼中闪过一丝" in ctx
        assert "不由得" in ctx

    def test_yaml_roundtrip(self):
        """YAML 读写往返"""
        narrator = NarratorCard(
            name="测试叙述者",
            one_line_pitch="一句话定位",
            daily_tone="日常语气",
            banned_phrases=["套话1", "套话2"],
        )
        tmp = tempfile.mktemp(suffix=".yaml")
        try:
            narrator.to_yaml(tmp)
            loaded = NarratorCard.from_yaml(tmp)
            assert loaded.name == narrator.name
            assert loaded.one_line_pitch == narrator.one_line_pitch
            assert loaded.daily_tone == narrator.daily_tone
            assert loaded.banned_phrases == narrator.banned_phrases
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_from_markdown_simple(self):
        """从简单 Markdown 加载"""
        md_content = """## 叙述者定位
一个冷眼旁观但偶尔毒舌的损友

## 日常语气
轻松场景下的叙述风格

## 禁用套话
- 心中涌起暖流
- 眼中闪过一丝
"""
        tmp = tempfile.mktemp(suffix=".md")
        try:
            Path(tmp).write_text(md_content, encoding="utf-8")
            narrator = NarratorCard.from_markdown(Path(tmp))
            assert narrator.one_line_pitch == "一个冷眼旁观但偶尔毒舌的损友"
            assert narrator.daily_tone == "轻松场景下的叙述风格"
            assert "心中涌起暖流" in narrator.banned_phrases
            assert "眼中闪过一丝" in narrator.banned_phrases
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_from_markdown_with_samples(self):
        """从包含风格样本的 Markdown 加载"""
        md_content = """## 叙述者定位
全知视角，双声道

## 日常语气
轻松吐槽

## 风格样本
### 日常
系统又弹任务了。这次是'今晚八点，去楼下便利店'。
### 高潮
他猛地站起身，眼神锐利如刀。
"""
        tmp = tempfile.mktemp(suffix=".md")
        try:
            Path(tmp).write_text(md_content, encoding="utf-8")
            narrator = NarratorCard.from_markdown(Path(tmp))
            assert narrator.one_line_pitch == "全知视角，双声道"
            assert "系统又弹任务了" in narrator.samples_daily
            assert "他猛地站起身" in narrator.samples_climax
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_from_markdown_not_exists(self):
        """从不存在的文件加载返回空卡"""
        narrator = NarratorCard.from_markdown(Path("/nonexistent/narrator.md"))
        assert narrator is not None
        assert narrator.name == "叙述者"

    def test_from_yaml_invalid_content(self):
        """from_yaml 处理无效 YAML"""
        tmp = tempfile.mktemp(suffix=".yaml")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("not a dict")
            with pytest.raises(Exception):
                NarratorCard.from_yaml(tmp)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
