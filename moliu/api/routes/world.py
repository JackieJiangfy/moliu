"""世界观管理 API — 通用 CRUD"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock
from moliu.data.schemas import WorldSetting

router = APIRouter()


class WorldResponse(BaseModel):
    world_name: str = ""
    era: str = ""
    genre: str = ""
    key_constraints: list[str] = []
    summary: str = ""


class WorldUpdate(BaseModel):
    world_name: str | None = None
    era: str | None = None
    genre: str | None = None
    key_constraints: list[str] | None = None
    summary: str | None = None


@router.get("/world", response_model=WorldResponse)
async def get_world(
    request: Request,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取世界观"""
    cfg = request.app.state.config
    world_path = cfg.resolve_data_dir(novel_id) / "world" / "world.yaml"

    if not world_path.exists():
        return WorldResponse()

    world = WorldSetting.from_yaml(world_path)
    return WorldResponse(
        world_name=world.world_name or "",
        era=world.era or "",
        genre=world.genre or "",
        key_constraints=world.key_constraints or [],
        summary=world.summary or "",
    )


@router.put("/world", response_model=WorldResponse)
async def update_world(
    request: Request,
    body: WorldUpdate,
    novel_id: int = Query(1, description="小说ID"),
):
    """更新世界观"""
    cfg = request.app.state.config
    world_path = cfg.resolve_data_dir(novel_id) / "world" / "world.yaml"

    async with novel_lock(novel_id):
        if world_path.exists():
            world = WorldSetting.from_yaml(world_path)
        else:
            world = WorldSetting()

        if body.world_name is not None:
            world.world_name = body.world_name
        if body.era is not None:
            world.era = body.era
        if body.genre is not None:
            world.genre = body.genre
        if body.key_constraints is not None:
            world.key_constraints = body.key_constraints
        if body.summary is not None:
            world.summary = body.summary

        world.to_yaml(world_path)

    return WorldResponse(
        world_name=world.world_name or "",
        era=world.era or "",
        genre=world.genre or "",
        key_constraints=world.key_constraints or [],
        summary=world.summary or "",
    )