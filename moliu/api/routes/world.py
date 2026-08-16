"""世界观管理 API — 通用 CRUD"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock
from moliu.data.schemas import WorldSetting

router = APIRouter()


class WorldResponse(BaseModel):
    era: str = ""
    core_rules: list[str] = []
    power_system: str = ""
    faction_summary: str = ""
    key_constraints: list[str] = []
    narrative_style: str = ""


class WorldUpdate(BaseModel):
    era: str | None = None
    core_rules: list[str] | None = None
    power_system: str | None = None
    faction_summary: str | None = None
    key_constraints: list[str] | None = None
    narrative_style: str | None = None


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
        era=world.era or "",
        core_rules=world.core_rules or [],
        power_system=world.power_system or "",
        faction_summary=world.faction_summary or "",
        key_constraints=world.key_constraints or [],
        narrative_style=world.narrative_style or "",
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

        if body.era is not None:
            world.era = body.era
        if body.core_rules is not None:
            world.core_rules = body.core_rules
        if body.power_system is not None:
            world.power_system = body.power_system
        if body.faction_summary is not None:
            world.faction_summary = body.faction_summary
        if body.key_constraints is not None:
            world.key_constraints = body.key_constraints
        if body.narrative_style is not None:
            world.narrative_style = body.narrative_style

        world.to_yaml(world_path)

    return WorldResponse(
        era=world.era or "",
        core_rules=world.core_rules or [],
        power_system=world.power_system or "",
        faction_summary=world.faction_summary or "",
        key_constraints=world.key_constraints or [],
        narrative_style=world.narrative_style or "",
    )