"""卷管理 API — 通用 CRUD + 章级大纲(P0-2)"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock
from moliu.data.schemas import ChapterPlan, VolumeIndex, VolumePlan
from moliu.engines.outline_engine import ChapterOutlineEngine

router = APIRouter()


def _get_index(request: Request, novel_id: int = 1) -> VolumeIndex:
    cfg = request.app.state.config
    path = cfg.resolve_data_dir(novel_id) / "volumes" / "index.json"
    if not path.exists():
        return VolumeIndex()
    return VolumeIndex.from_json(path)


def _save_index(request: Request, index: VolumeIndex, novel_id: int = 1) -> None:
    cfg = request.app.state.config
    path = cfg.resolve_data_dir(novel_id) / "volumes" / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    index.to_json(path)


# --- Request/Response 模型 ---

class VolumeCreate(BaseModel):
    name: str
    subtitle: str = ""
    chapter_start: int = 1
    chapter_end: int = 0
    summary: str = ""


class VolumeUpdate(BaseModel):
    name: str | None = None
    subtitle: str | None = None
    chapter_start: int | None = None
    chapter_end: int | None = None
    summary: str | None = None
    status: str | None = None


class VolumeResponse(BaseModel):
    id: int
    name: str
    subtitle: str
    chapter_start: int
    chapter_end: int
    summary: str
    status: str
    created_at: str
    updated_at: str


# --- Routes ---

@router.get("/volumes", response_model=list[VolumeResponse])
async def list_volumes(
    request: Request,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取所有卷"""
    index = _get_index(request, novel_id)
    return [
        VolumeResponse(
            id=v.id,
            name=v.name,
            subtitle=v.subtitle,
            chapter_start=v.chapter_start,
            chapter_end=v.chapter_end,
            summary=v.summary,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in sorted(index.volumes, key=lambda x: x.chapter_start)
    ]


@router.get("/volumes/{volume_id}", response_model=VolumeResponse)
async def get_volume(
    request: Request,
    volume_id: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取单个卷"""
    index = _get_index(request, novel_id)
    for v in index.volumes:
        if v.id == volume_id:
            return VolumeResponse(
                id=v.id, name=v.name, subtitle=v.subtitle,
                chapter_start=v.chapter_start, chapter_end=v.chapter_end,
                summary=v.summary, status=v.status,
                created_at=v.created_at, updated_at=v.updated_at,
            )
    raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")


@router.post("/volumes", response_model=VolumeResponse, status_code=201)
async def create_volume(
    request: Request,
    body: VolumeCreate,
    novel_id: int = Query(1, description="小说ID"),
):
    """创建新卷"""
    async with novel_lock(novel_id):
        index = _get_index(request, novel_id)
        now = datetime.now(timezone.utc).isoformat()

        new_id = max((v.id for v in index.volumes), default=0) + 1
        new_vol = VolumePlan(
            id=new_id,
            name=body.name,
            subtitle=body.subtitle,
            chapter_start=body.chapter_start,
            chapter_end=body.chapter_end,
            summary=body.summary,
            status="planned",
            created_at=now,
            updated_at=now,
        )
        index.volumes.append(new_vol)
        index.volumes.sort(key=lambda v: v.id)
        _save_index(request, index, novel_id)

    return VolumeResponse(
        id=new_vol.id, name=new_vol.name, subtitle=new_vol.subtitle,
        chapter_start=new_vol.chapter_start, chapter_end=new_vol.chapter_end,
        summary=new_vol.summary, status=new_vol.status,
        created_at=new_vol.created_at, updated_at=new_vol.updated_at,
    )


@router.put("/volumes/{volume_id}", response_model=VolumeResponse)
async def update_volume(
    request: Request,
    volume_id: int,
    body: VolumeUpdate,
    novel_id: int = Query(1, description="小说ID"),
):
    """更新卷信息"""
    async with novel_lock(novel_id):
        index = _get_index(request, novel_id)
        for v in index.volumes:
            if v.id == volume_id:
                if body.name is not None:
                    v.name = body.name
                if body.subtitle is not None:
                    v.subtitle = body.subtitle
                if body.chapter_start is not None:
                    v.chapter_start = body.chapter_start
                if body.chapter_end is not None:
                    v.chapter_end = body.chapter_end
                if body.summary is not None:
                    v.summary = body.summary
                if body.status is not None:
                    v.status = body.status
                v.updated_at = datetime.now(timezone.utc).isoformat()
                _save_index(request, index, novel_id)
                updated = v
                break
        else:
            raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")

    return VolumeResponse(
        id=updated.id, name=updated.name, subtitle=updated.subtitle,
        chapter_start=updated.chapter_start, chapter_end=updated.chapter_end,
        summary=updated.summary, status=updated.status,
        created_at=updated.created_at, updated_at=updated.updated_at,
    )


@router.delete("/volumes/{volume_id}", status_code=204)
async def delete_volume(
    request: Request,
    volume_id: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """删除卷"""
    async with novel_lock(novel_id):
        index = _get_index(request, novel_id)
        for i, v in enumerate(index.volumes):
            if v.id == volume_id:
                index.volumes.pop(i)
                _save_index(request, index, novel_id)
                return
        raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")


# === 章级大纲 (P0-2) ===

class ChapterPlanResponse(BaseModel):
    chapter_num: int
    title: str = ""
    beat: str = ""
    emotion: str = ""
    chapter_type: str = "normal"
    characters: list[str] = []
    key_events: list[str] = []
    foreshadows_plant: list[str] = []
    foreshadows_pay: list[str] = []
    status: str = "planned"


class ChapterPlanUpdate(BaseModel):
    title: str | None = None
    beat: str | None = None
    emotion: str | None = None
    chapter_type: str | None = None
    characters: list[str] | None = None
    key_events: list[str] | None = None
    foreshadows_plant: list[str] | None = None
    foreshadows_pay: list[str] | None = None
    status: str | None = None


class OutlineGenerateRequest(BaseModel):
    force: bool = False  # 是否强制覆盖已存在的大纲


class OutlineGenerateResponse(BaseModel):
    volume_id: int
    chapter_start: int
    chapter_end: int
    plans_count: int
    model_used: str
    tokens_used: int


def _get_outline_engine(request: Request, novel_id: int = 1) -> ChapterOutlineEngine:
    """构造大纲引擎(无 gateway,仅启发式)"""
    cfg = request.app.state.config
    gateway = getattr(request.app.state, "gateway", None)
    return ChapterOutlineEngine(cfg, novel_id=novel_id, gateway=gateway)


@router.get("/volumes/{volume_id}/outline", response_model=list[ChapterPlanResponse])
async def get_volume_outline(
    request: Request,
    volume_id: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取卷的章级大纲"""
    engine = _get_outline_engine(request, novel_id)
    plans = engine.load_volume_outline(volume_id)
    return [ChapterPlanResponse(**p.model_dump()) for p in plans]


@router.post(
    "/volumes/{volume_id}/outline/generate",
    response_model=OutlineGenerateResponse,
    status_code=201,
)
async def generate_volume_outline(
    request: Request,
    volume_id: int,
    body: OutlineGenerateRequest,
    novel_id: int = Query(1, description="小说ID"),
):
    """为卷生成章级大纲

    - 若 gateway 可用,使用 LLM 生成
    - 否则降级为启发式(节奏模板填充)
    - force=False 时若已存在大纲则直接返回缓存
    """
    engine = _get_outline_engine(request, novel_id)
    try:
        result = await engine.generate_for_volume(volume_id, force=body.force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return OutlineGenerateResponse(
        volume_id=result.volume_id,
        chapter_start=result.chapter_start,
        chapter_end=result.chapter_end,
        plans_count=len(result.plans),
        model_used=result.model_used,
        tokens_used=result.tokens_used,
    )


@router.put("/volumes/{volume_id}/outline/{chapter_num}", response_model=ChapterPlanResponse)
async def update_chapter_outline(
    request: Request,
    volume_id: int,
    chapter_num: int,
    body: ChapterPlanUpdate,
    novel_id: int = Query(1, description="小说ID"),
):
    """更新单章大纲字段"""
    engine = _get_outline_engine(request, novel_id)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="未提供任何更新字段")
    updated = engine.update_chapter_plan(chapter_num, **fields)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"章节 {chapter_num} 在卷 {volume_id} 的大纲中不存在",
        )
    return ChapterPlanResponse(**updated.model_dump())


@router.get("/outline/{chapter_num}", response_model=ChapterPlanResponse)
async def get_chapter_plan(
    request: Request,
    chapter_num: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """跨卷查找指定章节的大纲规划"""
    engine = _get_outline_engine(request, novel_id)
    plan = engine.get_chapter_plan(chapter_num)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"章节 {chapter_num} 无大纲规划")
    return ChapterPlanResponse(**plan.model_dump())


@router.get("/outline", response_model=dict)
async def get_outline_coverage(
    request: Request,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取大纲覆盖率统计"""
    engine = _get_outline_engine(request, novel_id)
    return engine.get_outline_coverage()