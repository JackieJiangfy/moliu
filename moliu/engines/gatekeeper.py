"""Gatekeeper — 生成前强制信息收集校验器

在生成任何章节前，必须通过此关卡。所有缺失信息会被列出并拒绝生成，
确保 LLM 始终拥有足够的上下文，避免内容跑偏。

使用方式:
    gatekeeper = Gatekeeper(config)
    result = await gatekeeper.check(chapter_num, ...)
    if not result.passed:
        print(result.missing_items)  # 列出所有缺失项
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from moliu.config import Config
from moliu.data.schemas import CharacterCard, ChapterMeta, VolumeIndex


@dataclass
class GatekeeperResult:
    """校验结果"""
    passed: bool = True
    missing_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context_hints: list[str] = field(default_factory=list)  # 有用的上下文提示

    def summary(self) -> str:
        if self.passed:
            return "[OK] Gatekeeper 校验通过"
        lines = ["[BLOCKED] 以下信息缺失，无法生成："]
        for item in self.missing_items:
            lines.append(f"  - {item}")
        if self.warnings:
            lines.append("[WARN] 以下信息建议补充：")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


class Gatekeeper:
    """生成前强制校验器 — 通用，不绑定具体小说"""

    def __init__(self, config: Config):
        self.config = config

    async def check(
        self,
        chapter_num: int,
        characters: list[CharacterCard],
        *,
        beat: str = "",
        emotion: str = "",
        force_check: bool = True,
    ) -> GatekeeperResult:
        """
        执行生成前强制校验

        Args:
            chapter_num: 目标章节号
            characters: 出场角色列表
            beat: 用户提供的节拍（可选，会在校验中告知缺失）
            emotion: 用户提供的情绪（可选）
            force_check: 是否强制执行检查（True=缺失则拒绝，False=仅警告）

        Returns:
            GatekeeperResult
        """
        result = GatekeeperResult()

        data_dir = self.config.resolve_data_dir()
        output_dir = self.config.resolve_output_dir()

        # ========== 1. 卷索引检查 ==========
        vol_index_path = data_dir / "volumes" / "index.json"
        if vol_index_path.exists():
            try:
                vol_index = VolumeIndex.from_json(vol_index_path)
                volume = vol_index.get_volume_for_chapter(chapter_num)
                if volume is None:
                    result.missing_items.append(
                        f"第 {chapter_num} 章未归属任何卷。"
                        f"请在 data/volumes/index.json 中定义卷的章节范围"
                    )
                elif not volume.name:
                    result.warnings.append(
                        f"第 {chapter_num} 章归属于卷 {volume.id}，但该卷未命名"
                    )
            except Exception as e:
                result.warnings.append(f"卷索引解析失败: {e}")
        else:
            result.warnings.append(
                f"卷索引不存在 (data/volumes/index.json)，"
                f"建议先规划卷结构"
            )

        # ========== 2. 章节大纲检查 ==========
        outline_dir = data_dir / "outlines"
        if outline_dir.exists():
            # 先通过卷索引找到大纲文件，再检查该章节是否在卷范围内
            chapter_found = False
            outline_file = None

            # 优先检查卷索引指定的大纲文件
            if vol_index_path.exists():
                try:
                    vol_index = VolumeIndex.from_json(vol_index_path)
                    volume = vol_index.get_volume_for_chapter(chapter_num)
                    if volume and volume.name:
                        # 尝试匹配大纲文件名（卷名可能不完全等于文件名）
                        for f in sorted(outline_dir.glob("*.yaml")):
                            chapter_found = self._check_chapter_in_outline(f, chapter_num)
                            if chapter_found:
                                outline_file = f
                                break
                except Exception:
                    pass

            # 如果卷索引没找到，扫描所有大纲文件
            if not chapter_found:
                for f in sorted(outline_dir.glob("*.yaml")):
                    chapter_found = self._check_chapter_in_outline(f, chapter_num)
                    if chapter_found:
                        outline_file = f
                        break

            if not chapter_found:
                # 检查该章是否在已完成的范围内（已生成的章节不需要大纲）
                existing_chapter = output_dir / f"第{chapter_num}章" / "正文.md"
                if existing_chapter.exists():
                    result.warnings.append(
                        f"第 {chapter_num} 章已有正文，大纲检查跳过"
                    )
                else:
                    result.missing_items.append(
                        f"第 {chapter_num} 章未在 data/outlines/ 中找到大纲定义。"
                        f"请先在大纲文件中定义本章节拍"
                    )

        # ========== 3. 节拍检查 ==========
        if not beat or len(beat.strip()) < 5:
            result.missing_items.append(
                f"缺少节拍描述（beat）。请提供一句话描述本章发生的事情"
            )

        # ========== 4. 出场角色检查 ==========
        if not characters:
            result.missing_items.append(
                f"未指定出场角色。请至少指定一个本章出场的角色"
            )
        else:
            # 检查角色状态是否最新
            chars_dir = output_dir / "characters"
            if chars_dir.exists():
                for c in characters:
                    char_file = chars_dir / f"{c.name}.yaml"
                    if not char_file.exists():
                        result.warnings.append(
                            f"角色「{c.name}」在 output/chapters/characters/ 中无状态记录，"
                            f"可能是新角色或状态未同步"
                        )

        # ========== 5. 上一章元数据检查 ==========
        if chapter_num > 1:
            prev_meta_path = output_dir / f"第{chapter_num - 1}章" / "meta.json"
            if prev_meta_path.exists():
                try:
                    prev_meta = ChapterMeta.from_json(prev_meta_path)
                    if not prev_meta.emotion and not emotion:
                        result.warnings.append(
                            f"第 {chapter_num - 1} 章缺少情绪标签，"
                            f"建议通过 --emotion 手动指定本章起始情绪"
                        )
                    if not prev_meta.key_events:
                        result.warnings.append(
                            f"第 {chapter_num - 1} 章缺少关键事件记录，"
                            f"建议先补全前文章节元数据"
                        )
                except Exception:
                    result.warnings.append(
                        f"第 {chapter_num - 1} 章 meta.json 解析失败"
                    )

        # ========== 6. 伏笔检查 ==========
        foreshadow_file = data_dir / "foreshadow.json"
        if foreshadow_file.exists():
            try:
                data = json.loads(foreshadow_file.read_text(encoding="utf-8"))
                active = [e for e in data if e.get("status") in ("planted", "building")]
                overdue = []
                for e in active:
                    planted = e.get("planted_chapter", 0)
                    age = chapter_num - planted
                    priority = e.get("priority", "normal")
                    if (priority == "high" and age > 20) or (age > 35):
                        overdue.append(e)

                if overdue:
                    hints = []
                    for e in overdue[:3]:
                        hints.append(
                            f"伏笔「{e.get('description', '')[:40]}」已埋 {chapter_num - e.get('planted_chapter', 0)} 章"
                        )
                    result.context_hints.append(
                        "以下伏笔已超期，如果本章合适请推进或回收：\n" + "\n".join(hints)
                    )
            except Exception:
                pass

        # ========== 7. 字数和配置检查 ==========
        if chapter_num < 1:
            result.missing_items.append("章节号必须 >= 1")

        # ========== 最终判定 ==========
        if force_check and result.missing_items:
            result.passed = False

        return result

    @staticmethod
    def format_checklist(chapter_num: int, beat: str, characters: list[CharacterCard]) -> str:
        """生成生成前 checklist 文案（用于提示用户）"""
        lines = [
            f"=== 第 {chapter_num} 章 生成前 Checklist ===",
            f"",
            f"[ ] 卷归属已定义（data/volumes/index.json）",
            f"[ ] 大纲已定义（data/outlines/）",
            f"[ ] 节拍已填写（当前: {beat or '未填写'}）",
            f"[ ] 出场角色已指定（当前: {len(characters)} 个）",
            f"[ ] 情绪标签已指定",
            f"[ ] 上一章元数据完整",
            f"[ ] 伏笔状态已检查",
            f"",
            f"全部打勾后才能生成。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _check_chapter_in_outline(filepath: Path, chapter_num: int) -> bool:
        """检查大纲文件中是否定义了指定章节

        支持以下格式：
        - "第N章" / "第 N 章" / "第N章：" 等变体
        - YAML 结构化大纲中的 chapter_num 字段
        """
        try:
            text = filepath.read_text(encoding="utf-8")
            # 方法1: 文本匹配（兼容 Markdown 风格大纲）
            import re
            patterns = [
                rf"第\s*{chapter_num}\s*章",
                rf"chapter.*{chapter_num}",
            ]
            for pat in patterns:
                if re.search(pat, text):
                    return True
            # 方法2: YAML 结构化解析
            try:
                import yaml
                data = yaml.safe_load(text)
                if isinstance(data, dict):
                    chapters = data.get("chapters", [])
                    if isinstance(chapters, list):
                        for ch in chapters:
                            if isinstance(ch, dict) and ch.get("num") == chapter_num:
                                return True
                            if isinstance(ch, dict) and ch.get("chapter_num") == chapter_num:
                                return True
            except Exception:
                pass
            return False
        except Exception:
            return False