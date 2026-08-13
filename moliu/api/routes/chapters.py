"""章节 API — 列表、获取、生成、编辑"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from moliu.data.schemas import ChapterMeta
from moliu.engines.gatekeeper import Gatekeeper

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


class GenerateCheckResponse(BaseModel):
    passed: bool
    missing_items: list[str] = []
    warnings: list[str] = []
    context_hints: list[str] = []


# --- 辅助函数 ---

def _get_chapter_meta(output_dir: Path, ch: int) -> ChapterMeta | None:
    meta_path = output_dir / f"第{ch}章" / "meta.json"
    if meta_path.exists():
        return ChapterMeta.from_json(meta_path)
    return None


def _get_chapter_content(output_dir: Path, ch: int) -> str:
    content_path = output_dir / f"第{ch}章" / "正文.md"
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
):
    """获取章节列表（分页）"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir()
    data_dir = cfg.resolve_data_dir()

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
async def get_chapter(request: Request, chapter_num: int):
    """获取单章详情"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir()
    data_dir = cfg.resolve_data_dir()

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
):
    """生成前预检 — Gatekeeper 强制信息收集校验"""
    cfg = request.app.state.config
    from moliu.cli.utils import load_characters

    all_chars = load_characters(cfg)
    char_names = [n.strip() for n in characters.split(",") if n.strip()]
    selected = [c for c in all_chars if c.name in char_names] if char_names else all_chars

    gatekeeper = Gatekeeper(cfg)
    result = await gatekeeper.check(
        chapter_num, selected,
        beat=beat, emotion=emotion,
        force_check=True,
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
):
    """手动更新章节正文（保存新版本）"""
    cfg = request.app.state.config
    output_dir = cfg.resolve_output_dir()
    chapter_dir = output_dir / f"第{chapter_num}章"

    if not chapter_dir.exists():
        raise HTTPException(status_code=404, detail=f"第{chapter_num}章不存在")

    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

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
async def get_chapter_versions(request: Request, chapter_num: int):
    """获取章节版本历史"""
    cfg = request.app.state.config
    chapter_dir = cfg.resolve_output_dir() / f"第{chapter_num}章"
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
async def restore_chapter(request: Request, chapter_num: int, body: dict):
    """回滚到指定版本"""
    cfg = request.app.state.config
    chapter_dir = cfg.resolve_output_dir() / f"第{chapter_num}章"
    versions_dir = chapter_dir / "versions"

    target_version = body.get("version")
    if not target_version:
        raise HTTPException(status_code=400, detail="需指定 version")

    source_path = versions_dir / f"v{target_version}.md"
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"版本 v{target_version} 不存在")

    current_path = chapter_dir / "正文.md"
    content = source_path.read_text(encoding="utf-8")
    current_path.write_text(content, encoding="utf-8")

    return {"ok": True, "chapter_num": chapter_num, "restored_version": target_version}


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

    all_characters = load_characters(config)
    if not all_characters:
        raise ValueError("没有找到角色文件")

    if characters_filter:
        characters = [c for c in all_characters if c.name in characters_filter]
    else:
        characters = all_characters

    world = load_world(config)
    narrator = load_narrator(config)

    gateway = DeepSeekGateway(config)
    prompts = PromptManager(config)

    checker = ConsistencyChecker(gateway)
    prechecker = AnchoredPreChecker(gateway)
    reader = ReaderEvaluator(gateway)
    tracker = RhythmTracker(config.resolve_data_dir())
    usage_tracker = UsageTracker(
        config.resolve_data_dir() / "usage_log.jsonl",
        monthly_budget=getattr(config, 'monthly_token_budget', 0),
    )
    gateway.usage_tracker = usage_tracker

    pipeline = ChapterPipeline(
        config, gateway, prompts,
        checker=checker, prechecker=prechecker,
        reader=reader, tracker=tracker,
    )

    # 1. 锚点预检
    pre_ok, pre_text = await pipeline.run_pre_check(beat, characters, chapter_num=chapter_num)

    # 2. 上下文组装
    assembler = StructuredAssembler(config)
    ctx = await assembler.assemble(
        chapter_num, beat, characters, world,
        narrator=narrator, narrator_guide="",
        last_emotion=emotion,
    )

    # 3. 生成
    result = await pipeline.generator.generate_chapter(
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
    )

    # 4. 去AI味
    detector = DeAIDetector()
    l1_report = detector.detect_l1(result.content)
    if l1_report.hard_violations or l1_report.overall_score < 0.8:
        rewriter = DeAIRewriter(gateway)
        try:
            rewritten = await rewriter.rewrite_flagged(
                result.content, l1_report.flagged_paragraphs[:3],
                chapter_num=chapter_num,
            )
            if rewritten != result.content:
                result = ChapterResult(
                    chapter_num=result.chapter_num,
                    content=rewritten,
                    word_count=count_words(rewritten),
                    model_used=result.model_used,
                    tokens_used=result.tokens_used,
                )
        except Exception:
            pass

    # 5. 质检
    qr = QualityReport()
    try:
        qr = await pipeline.run_quality_checks(result, beat, characters, world, narrator, chapter_num=chapter_num)
    except Exception:
        pass

    # 6. 落盘 + 记忆 + 节奏
    summary_text = await pipeline.generator._generate_summary_with_llm(result.content, chapter_num)
    clean_summary = summary_text.replace(f"第{chapter_num}章【摘要】", "")

    pipeline.save_meta(chapter_num, result, qr, clean_summary, emotion, characters)
    pipeline.save_to_memory(chapter_num, result, clean_summary, emotion, characters)
    pipeline.save_rhythm_record(chapter_num, result, qr, chapter_type, emotion)

    filepath = config.resolve_output_dir() / f"第{chapter_num}章" / "正文.md"

    return {
        "result": result,
        "filepath": str(filepath),
        "quality": qr,
    }


@router.post("/generate", response_model=GenerateResponse)
async def generate_chapter(request: Request, body: GenerateRequest):
    """生成单章（含 Gatekeeper 强制校验 + 完整管线）"""
    cfg = request.app.state.config
    from moliu.cli.utils import load_characters

    all_chars = load_characters(cfg)
    char_names = body.characters if body.characters else []
    selected = [c for c in all_chars if c.name in char_names] if char_names else all_chars

    # Gatekeeper 校验
    gatekeeper = Gatekeeper(cfg)
    gk = await gatekeeper.check(
        body.chapter_num, selected,
        beat=body.beat, emotion=body.emotion,
        force_check=True,
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


@router.websocket("/generate/stream")
async def generate_stream(ws: WebSocket):
    """WebSocket 流式生成 — 实时推送生成进度"""
    await ws.accept()
    try:
        # 等待客户端发送生成参数
        data = await ws.receive_json()
        chapter_num = data.get("chapter_num")
        beat = data.get("beat", "")
        emotion = data.get("emotion", "轻松")
        characters_filter = data.get("characters", [])
        chapter_type = data.get("chapter_type", "auto")
        temperature = data.get("temperature")

        if not chapter_num or not beat:
            await ws.send_json({"type": "error", "message": "缺少 chapter_num 或 beat"})
            await ws.close()
            return

        cfg = ws.app.state.config

        # 1. Gatekeeper 校验
        await ws.send_json({"type": "step", "step": "gatekeeper", "status": "running"})
        from moliu.cli.utils import load_characters
        all_chars = load_characters(cfg)
        selected = [c for c in all_chars if c.name in characters_filter] if characters_filter else all_chars

        gatekeeper = Gatekeeper(cfg)
        gk = await gatekeeper.check(
            chapter_num, selected,
            beat=beat, emotion=emotion,
            force_check=True,
        )
        if not gk.passed:
            await ws.send_json({
                "type": "gatekeeper_failed",
                "missing_items": gk.missing_items,
                "warnings": gk.warnings,
            })
            await ws.close()
            return

        await ws.send_json({"type": "step", "step": "gatekeeper", "status": "passed"})

        # 2. 执行生成
        await ws.send_json({"type": "step", "step": "generating", "status": "running"})
        try:
            gen = await _run_generation(
                cfg,
                chapter_num=chapter_num,
                beat=beat,
                emotion=emotion,
                characters_filter=characters_filter,
                chapter_type=chapter_type,
                temperature=temperature,
            )
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"生成失败: {str(e)[:200]}"})
            await ws.close()
            return

        result = gen["result"]
        qr = gen["quality"]

        # 3. 推送结果
        await ws.send_json({
            "type": "complete",
            "chapter_num": result.chapter_num,
            "word_count": result.word_count,
            "tokens_used": result.tokens_used,
            "content": result.content,
            "quality_report": qr.summary(),
            "filepath": gen["filepath"],
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)[:200]})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass