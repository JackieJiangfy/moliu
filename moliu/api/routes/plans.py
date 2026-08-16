"""创作意图规划 API — 把自然语言转为结构化章节蓝图"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock

router = APIRouter()


# --- Request/Response 模型 ---

class PlanRequest(BaseModel):
    """规划请求 — 作者的自然语言意图"""
    intent: str                # 自然语言创作意图
    novel_id: int = 1


class PlanResponse(BaseModel):
    """规划结果 — 结构化章节蓝图,用户确认后可调 /generate"""
    chapter_num: int
    beat: str
    emotion: str
    chapter_type: str
    characters: list[str]
    reason: str
    references: list[str]
    valid: bool                # 解析是否成功


# --- 路由 ---

@router.post("/plan", response_model=PlanResponse)
async def plan_chapter(request: Request, body: PlanRequest):
    """把自然语言意图拆解成结构化章节蓝图

    用户在前端输入自然语言（如"帮我推进到沈夜发现验钞机真相"），
    返回结构化的 chapter_num/beat/emotion/chapter_type 等。
    用户确认/微调后再调 /api/v1/generate。
    """
    if not body.intent.strip():
        raise HTTPException(status_code=422, detail="intent 不能为空")

    cfg = request.app.state.config

    # 用小说级锁,避免同一本小说并发规划时上下文不一致
    async with novel_lock(body.novel_id):
        from moliu.engines.gateway import DeepSeekGateway
        from moliu.engines.planner import Planner
        from moliu.prompts.manager import PromptManager

        prompts = PromptManager(cfg)
        # gateway 生命周期短,规划完即关
        async with DeepSeekGateway(cfg) as gateway:
            planner = Planner(cfg, gateway, prompts, novel_id=body.novel_id)
            plan = await planner.plan(body.intent)

    if not plan.is_valid():
        # 解析失败也返回结构,带 valid=False,让前端友好提示
        return PlanResponse(
            chapter_num=plan.chapter_num,
            beat=plan.beat,
            emotion=plan.emotion,
            chapter_type=plan.chapter_type,
            characters=plan.characters,
            reason=plan.reason or "规划失败,请重试或换一种描述",
            references=plan.references,
            valid=False,
        )

    return PlanResponse(
        chapter_num=plan.chapter_num,
        beat=plan.beat,
        emotion=plan.emotion,
        chapter_type=plan.chapter_type,
        characters=plan.characters,
        reason=plan.reason,
        references=plan.references,
        valid=True,
    )
