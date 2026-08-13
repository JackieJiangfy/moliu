"""角色管理 API — 通用 CRUD"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


class CharacterUpdate(BaseModel):
    one_line_pitch: str | None = None
    current_location: str | None = None
    current_goal: str | None = None
    current_emotion: str | None = None


@router.get("/characters", response_model=list[CharacterResponse])
async def list_characters(request: Request):
    """获取所有角色"""
    cfg = request.app.state.config
    char_dir = cfg.resolve_data_dir() / "characters"

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
        ))

    return characters


@router.get("/characters/{name}", response_model=CharacterResponse)
async def get_character(request: Request, name: str):
    """获取单个角色详情"""
    cfg = request.app.state.config
    char_path = cfg.resolve_data_dir() / "characters" / f"{name}.yaml"

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
    )


@router.put("/characters/{name}", response_model=CharacterResponse)
async def update_character(request: Request, name: str, body: CharacterUpdate):
    """更新角色状态"""
    cfg = request.app.state.config
    char_dir = cfg.resolve_data_dir() / "characters"
    char_path = char_dir / f"{name}.yaml"

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
    )