"""角色管理 API — 通用 CRUD"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock
from moliu.data.schemas import CharacterCard

router = APIRouter()


class CharacterResponse(BaseModel):
    name: str
    one_line_pitch: str
    core_desire: str
    surface_desire: str
    deep_fear: str
    current_location: str
    current_goal: str
    current_emotion: str
    status: str = "active"                      # 问题4: 角色状态(用于排序)
    last_chapter_appeared: int = 0              # 问题4: 最近出场章节(用于排序)


class CharacterUpdate(BaseModel):
    one_line_pitch: str | None = None
    current_location: str | None = None
    current_goal: str | None = None
    current_emotion: str | None = None


@router.get("/characters", response_model=list[CharacterResponse])
async def list_characters(
    request: Request,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取所有角色

    问题4: 排序依据明确化 — 按"状态优先级 + 最近出场章节倒序 + 文件名"组合排序
    1. 状态优先级:active(0) > injured(1) > missing(2) > left(3) > dead(4) > 其他(5)
       — 已死亡/离开的角色排最后,不干扰阅读
    2. 最近出场章节号倒序:出场越近越靠前(更"活跃"的角色优先)
    3. 文件名兜底:同状态同出场章的角色按文件名稳定排序
    """
    cfg = request.app.state.config
    char_dir = cfg.resolve_data_dir(novel_id) / "characters"

    # 状态优先级映射
    status_priority = {
        "active": 0,
        "injured": 1,
        "missing": 2,
        "left": 3,
        "dead": 4,
    }

    characters = []
    for f in sorted(char_dir.glob("*.yaml")):
        if f.name.endswith(".sample"):
            continue
        card = CharacterCard.from_yaml(f)
        characters.append(CharacterResponse(
            name=card.name,
            one_line_pitch=card.one_line_pitch or "",
            core_desire=card.core.core_desire if card.core else "",
            surface_desire=card.core.surface_desire if card.core else "",
            deep_fear=card.core.deep_fear if card.core else "",
            current_location=card.state.location if card.state else "",
            current_goal=card.state.current_goal if card.state else "",
            current_emotion=card.state.current_emotion if card.state else "",
            status=card.state.status if card.state else "active",
            last_chapter_appeared=card.state.last_chapter_appeared if card.state else 0,
        ))

    # 组合排序:状态优先级 → 出场章节倒序 → 名字
    characters.sort(
        key=lambda c: (
            status_priority.get(c.status, 5),
            -c.last_chapter_appeared,
            c.name,
        )
    )

    return characters


@router.get("/characters/{name}", response_model=CharacterResponse)
async def get_character(
    request: Request,
    name: str,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取单个角色详情"""
    cfg = request.app.state.config
    char_path = cfg.resolve_data_dir(novel_id) / "characters" / f"{name}.yaml"

    if not char_path.exists():
        raise HTTPException(status_code=404, detail=f"角色「{name}」不存在")

    card = CharacterCard.from_yaml(char_path)
    return CharacterResponse(
        name=card.name,
        one_line_pitch=card.one_line_pitch or "",
        core_desire=card.core.core_desire if card.core else "",
        surface_desire=card.core.surface_desire if card.core else "",
        deep_fear=card.core.deep_fear if card.core else "",
        current_location=card.state.location if card.state else "",
        current_goal=card.state.current_goal if card.state else "",
        current_emotion=card.state.current_emotion if card.state else "",
        status=card.state.status if card.state else "active",
        last_chapter_appeared=card.state.last_chapter_appeared if card.state else 0,
    )


@router.put("/characters/{name}", response_model=CharacterResponse)
async def update_character(
    request: Request,
    name: str,
    body: CharacterUpdate,
    novel_id: int = Query(1, description="小说ID"),
):
    """更新角色状态"""
    cfg = request.app.state.config
    char_dir = cfg.resolve_data_dir(novel_id) / "characters"
    char_path = char_dir / f"{name}.yaml"

    async with novel_lock(novel_id):
        if not char_path.exists():
            raise HTTPException(status_code=404, detail=f"角色「{name}」不存在")

        card = CharacterCard.from_yaml(char_path)

        if body.one_line_pitch is not None:
            card.one_line_pitch = body.one_line_pitch
        if body.current_location is not None and card.state:
            card.state.location = body.current_location
        if body.current_goal is not None and card.state:
            card.state.current_goal = body.current_goal
        if body.current_emotion is not None and card.state:
            card.state.current_emotion = body.current_emotion

        card.to_yaml(char_path)

    return CharacterResponse(
        name=card.name,
        one_line_pitch=card.one_line_pitch or "",
        core_desire=card.core.core_desire if card.core else "",
        surface_desire=card.core.surface_desire if card.core else "",
        deep_fear=card.core.deep_fear if card.core else "",
        current_location=card.state.location if card.state else "",
        current_goal=card.state.current_goal if card.state else "",
        current_emotion=card.state.current_emotion if card.state else "",
        status=card.state.status if card.state else "active",
        last_chapter_appeared=card.state.last_chapter_appeared if card.state else 0,
    )