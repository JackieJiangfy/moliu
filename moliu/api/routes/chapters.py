"""章节 API — 列表、获取、生成、编辑"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.config import Config
from moliu.data.schemas import ChapterMeta
from moliu.engines.gatekeeper import Gatekeeper
from moliu.api.locks import novel_lock

router = APIRouter()


# --- Response 模型 ---

class ChapterSummary(BaseModel):
    chapter_num: int
    title: str
    emotion: str
    word_count: int
    key_events: list[str]
    volume_id: int | None = None


class ChapterDetail(BaseModel):
    chapter_num: int
    title: str
    emotion: str
    content: str
    word_count: int
    key_events: list[str]
    summary: str
    volume_id: int | None = None


class ChapterListResponse(BaseModel):
    chapters: list[ChapterSummary]
    total: int
    start: int
    end: int


class GenerateRequest(BaseModel):
    chapter_num: int
    beat: str
    emotion: str = "轻松"
    characters: list[str] = []
    chapter_type: str = "auto"
    temperature: float | None = None
    novel_id: int = 1


class GenerateCheckResponse(BaseModel):
    passed: bool
    missing_items: list[str] = []
    warnings: list[str] = []
    context_hints: list[str] = []


# --- 辅助函数 ---

def _get_chapter_meta(output_dir: Path, ch: int) -> ChapterMeta | None:
    meta_path = output_dir / Config.chapter_dir_name(ch) / "meta.json"
    if meta_path.exists():
        return ChapterMeta.from_json(meta_path)
    return None


def _get_chapter_content(output_dir: Path, ch: int) -> str:
    content_path = output_dir / Config.chapter_dir_name(ch) / "正文.md"
    if content_path.exists():
        return content_path.read_text(encoding="utf-8")
    return ""


def _get_volume_for_chapter(data_dir: Path, ch: int) -> int | None:
    vol_path = data_dir / "volumes" / "index.json"
    if not vol_path.exists():
        return None
    try:
        data = json.loads(vol_path.read_text(encoding="utf-8"))
        for v in data.get("volumes", []):
            if v.get("chapter_start", 0) <= ch <= v.get("chapter_end", 0):
                return v.get("id")
    except Exception:
        pass
    return None


# --- Routes ---

@router.get("/chapters", response_model=ChapterListResponse)
async def list_chapters(
    request: Request,
    start: int = Query(1, ge=1, description="起始章节"),
    end: int = Query(50, ge=1, description="结束章节"),
    volume_id: int | None = Query(None, description="按卷筛选"),
    novel_id: int = Query(1, description="小说ID"),
):
    """获取章节列表（分页）"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir(novel_id)
    data_dir = cfg.resolve_data_dir(novel_id)

    chapters = []
    for ch in range(start, end + 1):
        meta = _get_chapter_meta(output_dir, ch)
        if meta is None:
            continue

        # 按卷筛选
        if volume_id is not None:
            vol = _get_volume_for_chapter(data_dir, ch)
            if vol != volume_id:
                continue

        chapters.append(ChapterSummary(
            chapter_num=ch,
            title=meta.title or f"第{ch}章",
            emotion=meta.emotion or "",
            word_count=meta.word_count or 0,
            key_events=meta.key_events or [],
            volume_id=_get_volume_for_chapter(data_dir, ch),
        ))

    return ChapterListResponse(
        chapters=chapters,
        total=len(chapters),
        start=start,
        end=end,
    )


@router.get("/chapters/{chapter_num}", response_model=ChapterDetail)
async def get_chapter(
    request: Request,
    chapter_num: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取单章详情"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir(novel_id)
    data_dir = cfg.resolve_data_dir(novel_id)

    meta = _get_chapter_meta(output_dir, chapter_num)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"第{chapter_num}章不存在")

    content = _get_chapter_content(output_dir, chapter_num)

    return ChapterDetail(
        chapter_num=chapter_num,
        title=meta.title or f"第{chapter_num}章",
        emotion=meta.emotion or "",
        content=content,
        word_count=meta.word_count or 0,
        key_events=meta.key_events or [],
        summary=meta.summary or "",
        volume_id=_get_volume_for_chapter(data_dir, chapter_num),
    )


@router.get("/generate/check", response_model=GenerateCheckResponse)
async def generate_check(
    request: Request,
    chapter_num: int = Query(..., description="目标章节号"),
    beat: str = Query("", description="节拍描述"),
    emotion: str = Query("轻松", description="情绪"),
    characters: str = Query("", description="出场角色列表，逗号分隔"),
    novel_id: int = Query(1, description="小说ID"),
):
    """生成前预检 — Gatekeeper 强制信息收集校验"""
    cfg = request.app.state.config
    from moliu.cli.utils import load_characters

    all_chars = load_characters(cfg, novel_id)
    char_names = [n.strip() for n in characters.split(",") if n.strip()]
    selected = [c for c in all_chars if c.name in char_names] if char_names else all_chars

    gatekeeper = Gatekeeper(cfg)
    result = await gatekeeper.check(
        chapter_num, selected,
        beat=beat, emotion=emotion,
        force_check=True, novel_id=novel_id,
    )

    return GenerateCheckResponse(
        passed=result.passed,
        missing_items=result.missing_items,
        warnings=result.warnings,
        context_hints=result.context_hints,
    )


@router.post("/chapters/{chapter_num}/content")
async def update_chapter_content(
    request: Request,
    chapter_num: int,
    body: dict,
    novel_id: int = Query(1, description="小说ID"),
):
    """手动更新章节正文（保存新版本）"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir(novel_id)
    chapter_dir = output_dir / Config.chapter_dir_name(chapter_num)

    if not chapter_dir.exists():
        raise HTTPException(status_code=404, detail=f"第{chapter_num}章不存在")

    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

    async with novel_lock(novel_id):
        # 保存版本
        versions_dir = chapter_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(versions_dir.glob("v*.md"))
        next_v = len(existing) + 1

        # 当前内容备份到版本目录
        current_path = chapter_dir / "正文.md"
        if current_path.exists():
            backup_path = versions_dir / f"v{next_v}.md"
            current_path.rename(backup_path)

        # 写入新内容
        current_path.write_text(content, encoding="utf-8")

        # 更新字数
        meta_path = chapter_dir / "meta.json"
        if meta_path.exists():
            meta = ChapterMeta.from_json(meta_path)
            meta.word_count = len(content)
            meta.to_json(meta_path)

    return {"ok": True, "chapter_num": chapter_num, "word_count": len(content), "version": next_v + 1}


@router.get("/chapters/{chapter_num}/versions")
async def get_chapter_versions(
    request: Request,
    chapter_num: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取章节版本历史"""
    cfg = request.app.state.config
    chapter_dir = cfg.resolve_output_dir(novel_id) / Config.chapter_dir_name(chapter_num)
    versions_dir = chapter_dir / "versions"

    if not versions_dir.exists():
        return {"versions": [], "current": None}

    versions = []
    for f in sorted(versions_dir.glob("v*.md")):
        try:
            v = int(f.stem[1:])
            versions.append({"version": v, "size": len(f.read_text(encoding="utf-8"))})
        except ValueError:
            continue

    # 当前版本内容大小
    current_path = chapter_dir / "正文.md"
    current_size = len(current_path.read_text(encoding="utf-8")) if current_path.exists() else 0

    return {
        "versions": versions,
        "current": {"version": len(versions) + 1, "size": current_size},
    }


@router.post("/chapters/{chapter_num}/restore")
async def restore_chapter(
    request: Request,
    chapter_num: int,
    body: dict,
    novel_id: int = Query(1, description="小说ID"),
):
    """回滚到指定版本"""
    cfg = request.app.state.config
    chapter_dir = cfg.resolve_output_dir(novel_id) / Config.chapter_dir_name(chapter_num)
    versions_dir = chapter_dir / "versions"

    target_version = body.get("version")
    if not target_version:
        raise HTTPException(status_code=400, detail="需指定 version")

    async with novel_lock(novel_id):
        source_path = versions_dir / f"v{target_version}.md"
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"版本 v{target_version} 不存在")

        current_path = chapter_dir / "正文.md"
        content = source_path.read_text(encoding="utf-8")
        current_path.write_text(content, encoding="utf-8")

    return {"ok": True, "chapter_num": chapter_num, "restored_version": target_version}


# --- 上下文预览 ---

@router.get("/chapters/{chapter_num}/context")
async def get_chapter_context(
    request: Request,
    chapter_num: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """预览生成第 N 章时将装配的上下文（不实际生成）

    返回：弧方向、角色状态、到期伏笔、约束、前章摘要、上一章收尾
    """
    cfg = request.app.state.config
    from moliu.cli.utils import load_characters, load_world, load_narrator
    from moliu.context.assembler import StructuredAssembler
    from moliu.data.schemas import WorldSetting

    try:
        all_chars = load_characters(cfg, novel_id)
        world = load_world(cfg, novel_id) or WorldSetting()
        narrator = load_narrator(cfg, novel_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载数据失败: {e}")

    try:
        assembler = StructuredAssembler(cfg)
        ctx = await assembler.assemble(
            chapter_num, "", all_chars, world,
            narrator=narrator, last_emotion="轻松",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上下文装配失败: {e}")

    # 卷归属
    vol_id = _get_volume_for_chapter(cfg.resolve_data_dir(novel_id), chapter_num)

    return {
        "chapter_num": chapter_num,
        "volume_id": vol_id,
        "arc_direction": ctx.arc_direction,
        "character_snapshots": ctx.character_snapshots,
        "due_foreshadows": ctx.due_foreshadows,
        "constraints": ctx.constraints,
        "recent_chapters_full": ctx.recent_chapters_full[:2000] + ("..." if len(ctx.recent_chapters_full) > 2000 else ""),
        "last_300_words": ctx.last_300_words,
        "recent_chars_count": len(ctx.recent_chapters_full),
    }


# --- 章节生成 ---

class GenerateResponse(BaseModel):
    ok: bool
    chapter_num: int
    title: str = ""
    word_count: int = 0
    tokens_used: int = 0
    content_preview: str = ""
    quality_report: str = ""
    filepath: str = ""


async def _run_generation(
    config,
    chapter_num: int,
    beat: str,
    emotion: str,
    characters_filter: list[str],
    chapter_type: str = "auto",
    temperature: float | None = None,
    segmented: bool = True,
    novel_id: int = 1,
) -> dict:
    """执行完整生成管线（复用 CLI write 逻辑）"""
    from moliu.cli.utils import load_characters, load_world, load_narrator
    from moliu.engines.gateway import DeepSeekGateway
    from moliu.prompts.manager import PromptManager
    from moliu.engines.checker import ConsistencyChecker, AnchoredPreChecker
    from moliu.engines.reader_eval import ReaderEvaluator
    from moliu.rules.rhythm_tracker import RhythmTracker
    from moliu.data.schemas import ChapterResult
    from moliu.engines.generator import count_words
    from moliu.orchestrator.pipeline import ChapterPipeline, QualityReport
    from moliu.engines.usage import UsageTracker
    from moliu.context.assembler import StructuredAssembler
    from moliu.deai.detector import DeAIDetector
    from moliu.deai.rewriter import DeAIRewriter

    all_characters = load_characters(config, novel_id)
    if not all_characters:
        raise ValueError("没有找到角色文件")

    if characters_filter:
        characters = [c for c in all_characters if c.name in characters_filter]
    else:
        characters = all_characters

    world = load_world(config, novel_id)
    narrator = load_narrator(config, novel_id)

    gateway = DeepSeekGateway(config)
    prompts = PromptManager(config)

    checker = ConsistencyChecker(gateway)
    prechecker = AnchoredPreChecker(gateway)
    reader = ReaderEvaluator(gateway)
    tracker = RhythmTracker(config.resolve_data_dir(novel_id))
    usage_tracker = UsageTracker(
        config.resolve_data_dir(novel_id) / "usage_log.jsonl",
        monthly_budget=getattr(config, 'monthly_token_budget', 0),
    )
    gateway.usage_tracker = usage_tracker

    pipeline = ChapterPipeline(
        config, gateway, prompts,
        checker=checker, prechecker=prechecker,
        reader=reader, tracker=tracker,
        novel_id=novel_id,
    )

    # P0-2: 若未传 beat 或 chapter_type=auto,从章级大纲读取
    from moliu.engines.outline_engine import ChapterOutlineEngine
    outline_engine = ChapterOutlineEngine(config, novel_id=novel_id, gateway=gateway)
    if not beat or chapter_type == "auto":
        plan = outline_engine.get_chapter_plan(chapter_num)
        if plan is not None:
            if not beat:
                beat = plan.beat
            if chapter_type == "auto":
                chapter_type = plan.chapter_type
            if not emotion or emotion == "轻松":
                # 用户未指定情绪时用大纲规划
                emotion = plan.emotion or "轻松"
            # 标记大纲状态为 generating
            outline_engine.mark_chapter_status(chapter_num, "generating")

    # 1. 锚点预检
    pre_ok, pre_text = await pipeline.run_pre_check(beat, characters, chapter_num=chapter_num)

    # 2. 上下文组装(注入分层记忆 P0-1)
    from moliu.memory.layered import LayeredMemory
    layered = LayeredMemory(config, novel_id=novel_id, gateway=gateway)
    assembler = StructuredAssembler(config, novel_id=novel_id, layered_memory=layered)
    ctx = await assembler.assemble(
        chapter_num, beat, characters, world,
        narrator=narrator, narrator_guide="",
        last_emotion=emotion,
    )

    # 3. 生成 + 4. 去AI味 + 5. 质检,不达标自动重试
    async def _generate_once():
        """单次生成 + 去AI味 — 返回 ChapterResult"""
        r = await pipeline.generator.generate_chapter(
            chapter_num=chapter_num,
            beat=beat,
            characters=characters,
            world=world,
            last_emotion=emotion,
            recent_chapters=ctx.recent_chapters_full,
            narrator_card=narrator,
            temperature=temperature,
            segmented=segmented,
            chapter_type=chapter_type,
            memory_context=ctx.layered_memory,
        )

        # 去AI味
        detector = DeAIDetector()
        l1_report = detector.detect_l1(r.content)
        if l1_report.hard_violations or l1_report.overall_score < 0.8:
            rewriter = DeAIRewriter(gateway)
            try:
                rewritten = await rewriter.rewrite_flagged(
                    r.content, l1_report.flagged_paragraphs[:3],
                    chapter_num=chapter_num,
                )
                if rewritten != r.content:
                    r = ChapterResult(
                        chapter_num=r.chapter_num,
                        content=rewritten,
                        word_count=count_words(rewritten),
                        model_used=r.model_used,
                        tokens_used=r.tokens_used,
                    )
            except Exception:
                pass
        return r

    async def _quality(r):
        qr = QualityReport()
        try:
            qr = await pipeline.run_quality_checks(r, beat, characters, world, narrator, chapter_num=chapter_num)
        except Exception:
            pass
        return qr

    retry_conditions = tuple(
        s.strip() for s in getattr(config, "quality_retry_on", "fatal").split(",")
        if s.strip()
    )
    result, qr = await pipeline.run_with_retry(
        generate_fn=_generate_once,
        quality_fn=_quality,
        max_retries=getattr(config, "quality_retry_max", 1),
        retry_on=retry_conditions,
        beat=beat,
        chapter_num=chapter_num,
        use_targeted_fix=True,
    )

    # 6. 落盘 + 记忆 + 节奏
    summary_text = await pipeline.generator._generate_summary_with_llm(result.content, chapter_num)
    clean_summary = summary_text.replace(f"第{chapter_num}章【摘要】", "")

    pipeline.save_meta(chapter_num, result, qr, clean_summary, emotion, characters)
    pipeline.save_to_memory(chapter_num, result, clean_summary, emotion, characters)
    pipeline.save_rhythm_record(chapter_num, result, qr, chapter_type, emotion)
    # 分层记忆(P0-1):每 10 章触发一次阶段摘要生成
    await pipeline.maybe_generate_arc_summary(chapter_num)

    # P1-1:自动提取并应用伏笔
    try:
        from moliu.engines.foreshadow_extractor import extract_and_apply_foreshadows
        plan = outline_engine.get_chapter_plan(chapter_num)
        fs_result, fs_stats = await extract_and_apply_foreshadows(
            config, novel_id, chapter_num, result.content,
            plan=plan, gateway=gateway,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("伏笔自动提取失败: %s", e)

    # P0-2:标记大纲状态为 completed
    try:
        outline_engine.mark_chapter_status(chapter_num, "completed")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("大纲状态更新失败: %s", e)

    filepath = config.resolve_output_dir(novel_id) / Config.chapter_dir_name(chapter_num) / "正文.md"

    return {
        "result": result,
        "filepath": str(filepath),
        "quality": qr,
    }


@router.post("/generate", response_model=GenerateResponse)
async def generate_chapter(request: Request, body: GenerateRequest):
    """生成单章（含 Gatekeeper 强制校验 + 完整管线）

    加锁防止同本小说并发生成 — 但允许不同小说并行生成。
    """
    cfg = request.app.state.config
    from moliu.cli.utils import load_characters

    async with novel_lock(body.novel_id):
        all_chars = load_characters(cfg, body.novel_id)
        char_names = body.characters if body.characters else []
        selected = [c for c in all_chars if c.name in char_names] if char_names else all_chars

        # Gatekeeper 校验
        gatekeeper = Gatekeeper(cfg)
        gk = await gatekeeper.check(
            body.chapter_num, selected,
            beat=body.beat, emotion=body.emotion,
            force_check=True, novel_id=body.novel_id,
        )
        if not gk.passed:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Gatekeeper 校验未通过",
                    "missing_items": gk.missing_items,
                    "warnings": gk.warnings,
                },
            )

        # 执行生成
        try:
            gen = await _run_generation(
                cfg,
                chapter_num=body.chapter_num,
                beat=body.beat,
                emotion=body.emotion,
                characters_filter=body.characters,
                chapter_type=body.chapter_type,
                temperature=body.temperature,
                novel_id=body.novel_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)[:200]}")

    result = gen["result"]
    qr = gen["quality"]

    return GenerateResponse(
        ok=True,
        chapter_num=result.chapter_num,
        word_count=result.word_count,
        tokens_used=result.tokens_used,
        content_preview=result.content[:200],
        quality_report=qr.summary(),
        filepath=gen["filepath"],
    )