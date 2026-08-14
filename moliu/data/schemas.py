"""数据模型 — 角色人设卡、世界观、章节上下文"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# === 角色人设卡 ===

class SpeechProfile(BaseModel):
    """说话风格"""
    style: str = ""
    sentence_length: str = ""
    tone: str = ""
    common_words: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)


class CharacterCore(BaseModel):
    """角色核心设定"""
    core_desire: str = ""             # 核心欲望
    surface_desire: str = ""          # 表层欲望
    deep_fear: str = ""               # 深层恐惧
    value_bottom_line: list[str] = Field(default_factory=list)  # 价值观底线


class CharacterState(BaseModel):
    """角色动态状态（每章更新）"""
    status: str = "active"     # active / injured / missing / dead / left
    location: str = ""
    current_goal: str = ""
    current_emotion: str = ""
    physical_state: str = ""
    resources: list[str] = Field(default_factory=list)
    known_info: list[str] = Field(default_factory=list)
    last_chapter_appeared: int = 0   # 最后出场章节号(0=未出场) — 供图谱上下文使用


class Appearance(BaseModel):
    """外观（绘图用）"""
    height: str = ""
    build: str = ""
    face: str = ""
    hair: str = ""
    typical_outfit: str = ""
    signature_gesture: str = ""


class CharacterCard(BaseModel):
    """完整角色人设卡"""
    name: str
    one_line_pitch: str = ""
    speech_profile: SpeechProfile = Field(default_factory=SpeechProfile)
    speech_samples: list[str] = Field(default_factory=list)
    inner_voice_style: str = ""
    core: CharacterCore = Field(default_factory=CharacterCore)
    backstory_summary: str = ""
    backstory_impact: str = ""
    hidden_clues: list[str] = Field(default_factory=list)
    state: CharacterState = Field(default_factory=CharacterState)
    appearance: Appearance = Field(default_factory=Appearance)
    _backup_path: Path | None = None  # 备份路径（私有字段）

    def set_backup_path(self, path: Path) -> None:
        """设置备份目录"""
        self._backup_path = path

    def backup(self, chapter_num: int) -> Path | None:
        """
        备份当前角色状态到备份目录

        Args:
            chapter_num: 当前章节号，用于备份文件名

        Returns:
            备份文件路径，如果备份失败返回 None
        """
        if not self._backup_path:
            return None

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._backup_path / "backups" / self.name
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"ch{chapter_num:03d}_{timestamp}.yaml"

        try:
            self.to_yaml(backup_file)
            return backup_file
        except Exception:
            return None

    def update_state_from_text(self, content: str, strict: bool = False) -> None:
        """
        从正文中提取角色状态变化并更新

        警告：此方法使用简单的关键词启发式提取，可能产生不准确的结果。
        建议在 LLM 提取不可用时作为 fallback 使用，或配合严格模式。

        Args:
            content: 章节正文内容
            strict: 严格模式，只在高置信度时更新状态（减少误判，但可能漏更新）
        """
        # 提取位置信息（简单的基于关键词的提取）
        # 严格模式下只匹配完整的位置描述模式
        if strict:
            # 严格模式：匹配 "在XX" 后跟标点或换行的模式
            import re
            location_patterns = [
                r"在([\u4e00-\u9fff]{2,10})[。！？，、\s]",
                r"来到([\u4e00-\u9fff]{2,10})[。！？，、\s]",
                r"走进([\u4e00-\u9fff]{2,10})[。！？，、\s]",
            ]
            for pattern in location_patterns:
                match = re.search(pattern, content)
                if match:
                    location = match.group(1).strip()
                    if location and len(location) >= 2:
                        self.state.location = location
                        break
        else:
            # 宽松模式：简单关键词匹配
            location_keywords = ["来到", "走进", "离开", "返回", "前往", "到达"]
            for keyword in location_keywords:
                idx = content.find(keyword)
                if idx != -1:
                    end_idx = idx + len(keyword)
                    while end_idx < len(content):
                        char = content[end_idx]
                        if char in "。！？，、\n\r":
                            break
                        end_idx += 1
                    if end_idx > idx + len(keyword):
                        location = content[idx + len(keyword):end_idx].strip()
                        if location and len(location) >= 2 and len(location) < 50:
                            self.state.location = location
                            break

        # 提取情绪信息（严格模式下不更新，避免误判）
        if not strict:
            emotion_keywords = {
                "愤怒": ["愤怒", "怒", "生气", "恼火", "火大"],
                "悲伤": ["悲伤", "伤心", "难过", "流泪", "痛哭"],
                "开心": ["开心", "高兴", "快乐", "兴奋", "喜悦"],
                "惊讶": ["惊讶", "吃惊", "震惊", "愣住", "愕然"],
                "紧张": ["紧张", "焦虑", "不安", "忐忑", "惶恐"],
                "平静": ["平静", "冷静", "淡然", "镇定", "沉稳"],
            }
            for emotion, keywords in emotion_keywords.items():
                for keyword in keywords:
                    if keyword in content:
                        self.state.current_emotion = emotion
                        break
                if self.state.current_emotion:
                    break

        # 提取已知信息（严格模式下不更新，避免误判）
        if not strict:
            knowledge_keywords = ["知道了", "了解到", "意识到", "发现", "明白", "清楚"]
            for keyword in knowledge_keywords:
                idx = content.find(keyword)
                if idx != -1:
                    end_idx = idx + len(keyword)
                    while end_idx < len(content):
                        char = content[end_idx]
                        if char in "。！？，、\n\r":
                            break
                        end_idx += 1
                    if end_idx > idx + len(keyword):
                        info = content[idx + len(keyword):end_idx].strip()
                        if info and len(info) < 100 and info not in self.state.known_info:
                            self.state.known_info.append(info)
                            break

    def to_context(self) -> str:
        """将角色卡渲染为注入 Prompt 的上下文字符串"""
        parts = []
        parts.append(f"【{self.name}】{self.one_line_pitch}")

        sp = self.speech_profile
        speech_parts = []
        if sp.style:
            speech_parts.append(sp.style)
        if sp.sentence_length:
            speech_parts.append(sp.sentence_length)
        if sp.tone:
            speech_parts.append(sp.tone)
        if speech_parts:
            parts.append(f"说话风格: {'。'.join(speech_parts)}")
        if sp.common_words:
            parts.append(f"常用词: {' / '.join(sp.common_words)}")
        if sp.banned_words:
            parts.append(f"禁用词: {' / '.join(sp.banned_words)}")

        if self.inner_voice_style:
            parts.append(f"内心戏风格: {self.inner_voice_style}")

        if self.speech_samples:
            samples = "\n".join(f"  - {s}" for s in self.speech_samples)
            parts.append(f"说话样本:\n{samples}")
        if self.core.core_desire:
            parts.append(f"核心欲望: {self.core.core_desire}")
        if self.core.surface_desire:
            parts.append(f"表层欲望: {self.core.surface_desire}")
        if self.core.deep_fear:
            parts.append(f"深层恐惧: {self.core.deep_fear}")
        if self.core.value_bottom_line:
            parts.append(f"底线: {' / '.join(self.core.value_bottom_line)}")

        state_parts = []
        if self.state.location:
            state_parts.append(f"在{self.state.location}")
        if self.state.current_goal:
            state_parts.append(f"目标: {self.state.current_goal}")
        if self.state.current_emotion:
            state_parts.append(f"情绪: {self.state.current_emotion}")
        if state_parts:
            parts.append(f"当前状态: {'，'.join(state_parts)}")
        if self.state.resources:
            parts.append(f"持有: {' / '.join(self.state.resources)}")
        if self.state.known_info:
            parts.append(f"已知信息: {'; '.join(self.state.known_info)}")
        if self.state.physical_state:
            parts.append(f"身体状态: {self.state.physical_state}")

        if self.backstory_summary:
            parts.append(f"背景: {self.backstory_summary}")
        if self.hidden_clues:
            parts.append(f"隐藏线索: {'; '.join(self.hidden_clues)}")

        return "\n".join(parts)

    @classmethod
    def from_yaml(cls, path: Path) -> "CharacterCard":
        """从 YAML 文件加载角色卡"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"角色文件格式错误: {path} (期望 YAML dict)")
        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """保存角色卡到 YAML 文件"""
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )


# === 世界观 ===

class WorldSetting(BaseModel):
    """世界观设定"""
    era: str = ""
    core_rules: list[str] = Field(default_factory=list)
    power_system: str = ""
    faction_summary: str = ""
    key_constraints: list[str] = Field(default_factory=list)
    narrative_style: str = ""

    def to_context(self) -> str:
        """渲染为 Prompt 上下文"""
        parts = ["【世界观】"]
        if self.era:
            parts.append(f"时代: {self.era}")
        if self.core_rules:
            parts.append("核心规则:")
            for r in self.core_rules:
                parts.append(f"  - {r}")
        if self.power_system:
            parts.append(f"力量体系: {self.power_system}")
        if self.faction_summary:
            parts.append(f"势力概况: {self.faction_summary}")
        if self.key_constraints:
            parts.append("硬约束:")
            for c in self.key_constraints:
                parts.append(f"  - {c}")
        if self.narrative_style:
            parts.append(f"叙事基调: {self.narrative_style}")
        return "\n".join(parts)

    @classmethod
    def from_yaml(cls, path: Path) -> "WorldSetting":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"世界观文件格式错误: {path} (期望 YAML dict)")
        return cls(**data)


# === 叙述者 ===

class NarratorCard(BaseModel):
    """叙述者人设卡 - 定义叙事风格和规则"""
    name: str = "叙述者"
    one_line_pitch: str = ""          # 一句话定位
    daily_tone: str = ""              # 日常语气
    climax_tone: str = ""             # 高潮语气
    emotional_tone: str = ""          # 情绪戏语气
    sentence_features: list[str] = Field(default_factory=list)  # 句式特征
    banned_phrases: list[str] = Field(default_factory=list)     # 禁用套话
    samples_daily: str = ""           # 日常场景样本
    samples_climax: str = ""          # 高潮场景样本
    samples_emotional: str = ""       # 情绪戏样本
    perspective: str = ""             # 视角定位（全知/限知/第一人称等）
    language_style: str = ""          # 语言风格

    def to_context(self) -> str:
        """渲染为 Prompt 上下文"""
        parts = [f"【{self.name}】"]
        
        if self.one_line_pitch:
            parts.append(f"定位: {self.one_line_pitch}")
        
        if self.perspective:
            parts.append(f"视角: {self.perspective}")
        
        if self.language_style:
            parts.append(f"语言风格: {self.language_style}")
        
        if self.daily_tone:
            parts.append(f"日常语气: {self.daily_tone}")
        
        if self.climax_tone:
            parts.append(f"高潮语气: {self.climax_tone}")
        
        if self.emotional_tone:
            parts.append(f"情绪语气: {self.emotional_tone}")
        
        if self.sentence_features:
            parts.append("句式特征:")
            for feature in self.sentence_features:
                parts.append(f"  - {feature}")
        
        if self.banned_phrases:
            parts.append(f"禁用套话: {' / '.join(self.banned_phrases)}")
        
        if self.samples_daily:
            parts.append(f"日常样本:\n{self.samples_daily}")
        
        if self.samples_climax:
            parts.append(f"高潮样本:\n{self.samples_climax}")
        
        if self.samples_emotional:
            parts.append(f"情绪样本:\n{self.samples_emotional}")
        
        return "\n".join(parts)

    @classmethod
    def from_markdown(cls, path: Path) -> "NarratorCard":
        """从 Markdown 文件加载叙述者风格"""
        if not path.exists():
            return cls()
        
        content = path.read_text(encoding="utf-8")
        card = cls()
        
        # 解析 Markdown 结构
        lines = content.split("\n")
        current_section = ""
        section_content = []
        
        for line in lines:
            if line.startswith("## "):
                # 保存上一个 section
                if current_section:
                    card._set_section(current_section, "\n".join(section_content).strip())
                current_section = line[3:].strip()
                section_content = []
            else:
                section_content.append(line)
        
        # 保存最后一个 section
        if current_section:
            card._set_section(current_section, "\n".join(section_content).strip())
        
        return card

    def _set_section(self, name: str, content: str) -> None:
        """根据 section 名称设置字段"""
        content = content.strip()
        if not content:
            return
        
        if "叙述者定位" in name:
            self.one_line_pitch = content
        elif "日常语气" in name:
            self.daily_tone = content
        elif "高潮语气" in name:
            self.climax_tone = content
        elif "情绪戏语气" in name:
            self.emotional_tone = content
        elif "句式特征" in name:
            # 解析列表格式
            items = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    items.append(line[2:])
                elif line and not line.startswith("#"):
                    items.append(line)
            self.sentence_features = items
        elif "禁用套话" in name:
            # 解析列表格式
            items = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    items.append(line[2:])
                elif line and not line.startswith("#"):
                    items.append(line)
            self.banned_phrases = items
        elif "风格样本" in name:
            # 使用正则表达式提取样本，支持多种 AI 输出格式
            import re
            
            # 匹配模式：### [样本: ]日常/高潮/情绪...\n内容...
            # 支持: ### 日常, ### 样本: 日常, ### 样本：日常场景 等格式
            patterns = [
                (r"###\s*(?:样本[:：]\s*)?日常(?:[^\n]*)\n(.+?)(?=###|\Z)", "daily"),
                (r"###\s*(?:样本[:：]\s*)?高潮(?:[^\n]*)\n(.+?)(?=###|\Z)", "climax"),
                (r"###\s*(?:样本[:：]\s*)?情绪(?:[^\n]*)\n(.+?)(?=###|\Z)", "emotional"),
            ]
            
            for pattern, attr in patterns:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    sample_content = match.group(1).strip()
                    # 清理多余的空白和标记
                    sample_content = re.sub(r"\s+", " ", sample_content)
                    if attr == "daily":
                        self.samples_daily = sample_content
                    elif attr == "climax":
                        self.samples_climax = sample_content
                    elif attr == "emotional":
                        self.samples_emotional = sample_content

    @classmethod
    def from_yaml(cls, path: Path) -> "NarratorCard":
        """从 YAML 文件加载叙述者卡"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"叙述者文件格式错误: {path} (期望 YAML dict)")
        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """保存叙述者卡到 YAML 文件"""
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )


# === 章节产出 ===

class ChapterResult(BaseModel):
    """一章的生成结果"""
    chapter_num: int
    content: str
    word_count: int
    model_used: str
    tokens_used: int


# === 章节元数据 ===

class ChapterMeta(BaseModel):
    """章节元数据 - 用于 RAG 回忆和前文回灌"""
    chapter_num: int
    title: str = ""
    word_count: int
    tokens_used: int
    emotion: str = ""
    summary: str = ""              # 章节摘要（用于 RAG）
    key_characters: list[str] = Field(default_factory=list)  # 出场关键角色
    key_events: list[str] = Field(default_factory=list)      # 关键事件
    first_sentence: str = ""
    last_sentence: str = ""
    created_at: str = ""           # ISO 格式时间戳
    updated_at: str = ""           # ISO 格式时间戳

    def to_context(self) -> str:
        """渲染为前文回顾上下文"""
        parts = []
        if self.chapter_num:
            parts.append(f"第{self.chapter_num}章")
        if self.title:
            parts.append(f"{self.title}")
        if self.summary:
            parts.append(f"【摘要】{self.summary}")
        if self.key_events:
            parts.append(f"【关键事件】{'；'.join(self.key_events)}")
        if self.key_characters:
            parts.append(f"【出场角色】{'、'.join(self.key_characters)}")
        return "\n".join(parts)

    @classmethod
    def from_json(cls, path: Path) -> "ChapterMeta":
        """从 JSON 文件加载"""
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, path: Path) -> None:
        """保存到 JSON 文件"""
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, ensure_ascii=False, indent=2)


# === 卷/弧/章 规划模型（通用） ===

class ArcPlan(BaseModel):
    """故事弧 — 一个角色或故事线的成长轨迹（通用，不绑定具体小说）"""
    name: str
    type: str = "character"        # character / story / relationship
    description: str = ""
    start_chapter: int = 1
    end_chapter: int = 0
    milestones: list[str] = Field(default_factory=list)  # 关键里程碑事件
    status: str = "planned"        # planned / active / completed / abandoned


class ChapterPlan(BaseModel):
    """单章大纲 — 通用的章节规划"""
    chapter_num: int
    title: str = ""
    beat: str = ""                 # 本章节拍（一句话描述）
    emotion: str = ""              # 情绪标签
    chapter_type: str = "normal"   # opening / normal / climax / transition / epilogue
    characters: list[str] = Field(default_factory=list)  # 出场角色
    key_events: list[str] = Field(default_factory=list)  # 关键事件
    foreshadows_plant: list[str] = Field(default_factory=list)    # 本章埋入的伏笔
    foreshadows_pay: list[str] = Field(default_factory=list)      # 本章回收的伏笔
    status: str = "planned"        # planned / generating / completed / revised


class VolumePlan(BaseModel):
    """卷规划 — 通用的小说卷模型"""
    id: int
    name: str = ""
    subtitle: str = ""
    chapter_start: int = 1
    chapter_end: int = 0
    summary: str = ""
    arcs: list[ArcPlan] = Field(default_factory=list)
    chapters: list[ChapterPlan] = Field(default_factory=list)
    status: str = "planned"        # planned / active / completed
    created_at: str = ""
    updated_at: str = ""

    def to_yaml(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude={"chapters"}),  # 大纲文件不包含逐章详情
                f, allow_unicode=True, default_flow_style=False, sort_keys=False,
            )

    @classmethod
    def from_yaml(cls, path: Path) -> "VolumePlan":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


class VolumeIndex(BaseModel):
    """卷索引 — 一本小说的所有卷的索引（通用）"""
    novel_title: str = ""
    volumes: list[VolumePlan] = Field(default_factory=list)

    def get_volume_for_chapter(self, chapter_num: int) -> VolumePlan | None:
        for v in self.volumes:
            if v.chapter_start <= chapter_num <= v.chapter_end:
                return v
        return None

    @classmethod
    def from_json(cls, path: Path) -> "VolumeIndex":
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, path: Path) -> None:
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, ensure_ascii=False, indent=2)


# === 小说实体(多本支持) ===

class Novel(BaseModel):
    """小说实体 — 平台支持多本小说,每本独立数据目录"""
    id: int
    title: str
    subtitle: str = ""
    genre: str = ""                          # 题材:都市/玄幻/科幻...
    premise: str = ""                        # 一句话核心设定
    target_chapters: int = 1000
    status: str = "planned"                  # planned / active / completed / archived
    created_at: str = ""
    updated_at: str = ""


class NovelIndex(BaseModel):
    """小说索引 — data/novels/index.json,管理所有小说"""
    novels: list[Novel] = Field(default_factory=list)
    next_id: int = 1

    def get(self, novel_id: int) -> Novel | None:
        return next((n for n in self.novels if n.id == novel_id), None)

    @classmethod
    def from_json(cls, path: Path) -> "NovelIndex":
        import json
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, path: Path) -> None:
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, ensure_ascii=False, indent=2)


# === CLI 输出 ===

class GenerationReport(BaseModel):
    """生成报告（终端显示用）"""
    chapter_num: int
    word_count: int
    tokens_used: int
    first_sentence: str
    last_sentence: str
