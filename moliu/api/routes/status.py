"""状态概览 API"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ProjectStatus(BaseModel):
    novel_title: str = ""
    total_chapters: int = 0
    total_volumes: int = 0
    total_characters: int = 0
    total_words: int = 0
    latest_chapter: int = 0
    target_chapters: int = 1000
    progress_percent: float = 0.0
    missing_title: int = 0
    missing_emotion: int = 0
    missing_events: int = 0


@router.get("/status", response_model=ProjectStatus)
async def get_status(request: Request):
    """获取项目概览"""
    cfg = request.app.state.config
    data_dir = cfg.resolve_data_dir()
    output_dir = cfg.resolve_output_dir()

    # 小说名
    novel_title = ""
    vol_index_path = data_dir / "volumes" / "index.json"
    if vol_index_path.exists():
        import json
        data = json.loads(vol_index_path.read_text(encoding="utf-8"))
        novel_title = data.get("novel_title", "")

    # 章节
    existing = sorted(output_dir.glob("第*章"))
    total_chapters = len(existing)
    latest_chapter = 0
    total_words = 0
    missing_title = 0
    missing_emotion = 0
    missing_events = 0

    for d in existing:
        try:
            ch = int(d.name.replace("第", "").replace("章", ""))
            latest_chapter = max(latest_chapter, ch)
        except ValueError:
            continue

        # 字数统计
        content_file = d / "正文.md"
        if content_file.exists():
            total_words += len(content_file.read_text(encoding="utf-8"))

        # 元数据缺失统计
        meta_file = d / "meta.json"
        if meta_file.exists():
            import json
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if not meta.get("title") or meta.get("title") == f"第{ch}章":
                missing_title += 1
            if not meta.get("emotion"):
                missing_emotion += 1
            if not meta.get("key_events"):
                missing_events += 1
        else:
            missing_title += 1
            missing_emotion += 1
            missing_events += 1

    # 卷
    total_volumes = 0
    if vol_index_path.exists():
        import json
        data = json.loads(vol_index_path.read_text(encoding="utf-8"))
        total_volumes = len(data.get("volumes", []))

    # 角色
    char_dir = data_dir / "characters"
    total_characters = len([f for f in char_dir.glob("*.yaml") if not f.name.endswith(".sample")])

    progress = (total_chapters / 1000) * 100 if total_chapters > 0 else 0.0

    return ProjectStatus(
        novel_title=novel_title,
        total_chapters=total_chapters,
        total_volumes=total_volumes,
        total_characters=total_characters,
        total_words=total_words,
        latest_chapter=latest_chapter,
        target_chapters=1000,
        progress_percent=round(progress, 1),
        missing_title=missing_title,
        missing_emotion=missing_emotion,
        missing_events=missing_events,
    )