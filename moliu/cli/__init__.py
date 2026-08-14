"""墨流 CLI — 入口"""

import asyncio
import logging
from pathlib import Path

import typer

from .steps import check_continue, step_characters, step_direction, step_narrator, step_world
from .utils import QuickstartRollback, load_characters, load_config, load_narrator, load_world
from moliu.config import Config
from moliu.engines.generator import Generator
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.usage import UsageTracker
from moliu.prompts.manager import PromptManager

# 配置 logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = typer.Typer(
    name="mo",
    help="墨流 - AI 小说创作工作流引擎",
    no_args_is_help=True,
)


# === commands ===

@app.command()
def status():
    """查看项目状态: 角色数、已有章节数、世界观概况"""
    config = load_config()
    characters = load_characters(config)
    world = load_world(config)
    output_dir = config.resolve_output_dir()
    existing_chapters = sorted(
        d for d in output_dir.iterdir()
        if d.is_dir() and Config.parse_chapter_num(d.name) is not None
    )

    typer.echo("=== 墨流 项目状态 ===")
    typer.echo(f"世界观: {'[OK] 已设置' if world else '[MISS] 未创建'}")
    typer.echo(f"角色: {len(characters)} 个")
    if characters:
        for c in characters:
            typer.echo(f"  - {c.name}: {c.one_line_pitch or '(无定位)'}")
    typer.echo(f"已生成章节: {len(existing_chapters)} 章")
    if existing_chapters:
        typer.echo(f"  最新: {existing_chapters[-1].name}")


@app.command()
def write(
    chapter_num: int = typer.Argument(..., help="章节号"),
    beat: str = typer.Argument(..., help="本章节拍，一句话描述"),
    emotion: str = typer.Option("轻松", "--emotion", "-e", help="上一章收尾情绪"),
    recent: str = typer.Option("", "--recent", "-r", help="前文回顾文本"),
    characters_filter: str = typer.Option(
        "", "--characters", "-c",
        help="本章出场角色名，逗号分隔（留空则全部出场）",
    ),
    temperature: float = typer.Option(
        None, "--temperature", "-t",
        help="生成 temperature (0-2)，留空使用默认值",
    ),
    segmented: bool = typer.Option(True, "--segmented/--no-segmented", help="是否使用分段生成（三幕结构）"),
    chapter_type: str = typer.Option(
        "auto", "--chapter-type",
        help="章节类型: auto/normal/opening/setup/climax/transition/epilogue",
    ),
):
    """生成一章正文"""
    config = load_config()

    all_characters = load_characters(config)
    if not all_characters:
        typer.echo("[ERROR] 没有找到角色文件。请先在 data/characters/ 下创建角色 YAML")
        raise typer.Exit(code=1)

    # 按名称筛选出场角色
    if characters_filter:
        filter_names = [n.strip() for n in characters_filter.split(",")]
        characters = [c for c in all_characters if c.name in filter_names]
        missing = set(filter_names) - {c.name for c in characters}
        if missing:
            typer.echo(f"[WARN] 以下角色未找到: {', '.join(missing)}")
        if not characters:
            typer.echo("[ERROR] 筛选后无出场角色")
            raise typer.Exit(code=1)
    else:
        characters = all_characters

    world = load_world(config)
    if not world:
        typer.echo("[ERROR] 没有找到世界观文件。请先在 data/world/world.yaml 创建世界观")
        raise typer.Exit(code=1)

    narrator = load_narrator(config)

    # 校验 temperature
    if temperature is not None and not (0 <= temperature <= 2):
        typer.echo("[ERROR] temperature 必须在 0-2 之间")
        raise typer.Exit(code=1)

    # ========== Gatekeeper 强制信息收集校验 ==========
    import asyncio
    from moliu.engines.gatekeeper import Gatekeeper

    gatekeeper = Gatekeeper(config)
    gk_result = asyncio.run(gatekeeper.check(
        chapter_num, characters,
        beat=beat, emotion=emotion,
        force_check=True,
    ))

    if not gk_result.passed:
        typer.echo("")
        typer.echo(gk_result.summary())
        typer.echo("")
        typer.echo("请补充以上缺失信息后重试。")
        if gk_result.context_hints:
            for hint in gk_result.context_hints:
                typer.echo(f"  [提示] {hint}")
        raise typer.Exit(code=1)
    else:
        typer.echo(f"[OK] Gatekeeper 校验通过")
        if gk_result.warnings:
            for w in gk_result.warnings:
                typer.echo(f"  [WARN] {w}")
        if gk_result.context_hints:
            typer.echo("")
            for hint in gk_result.context_hints:
                typer.echo(f"  [提示] {hint}")

    typer.echo(f"=== 第 {chapter_num} 章 ===")
    typer.echo(f"节拍: {beat}")
    typer.echo(f"出场角色: {', '.join(c.name for c in characters)}")
    typer.echo(f"上一章情绪: {emotion}")
    if temperature is not None:
        typer.echo(f"Temperature: {temperature}")
    typer.echo("生成中...", nl=False)

    async def _run():
        gateway = DeepSeekGateway(config)
        prompts = PromptManager(config)

        from moliu.engines.checker import ConsistencyChecker, AnchoredPreChecker
        from moliu.engines.reader_eval import ReaderEvaluator
        from moliu.rules.rhythm_tracker import RhythmTracker
        from moliu.data.schemas import ChapterResult
        from moliu.engines.generator import count_words
        from moliu.orchestrator.pipeline import ChapterPipeline, QualityReport
        from moliu.engines.usage import UsageTracker
        from moliu.context.assembler import StructuredAssembler

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

        # 1. 角色锚点预检
        pre_ok, pre_text = await pipeline.run_pre_check(beat, characters, chapter_num=chapter_num)
        if not pre_ok:
            typer.echo(f"\r[WARN] 锚点预检: {pre_text[:100]}")
        else:
            typer.echo(f"\r[OK] 锚点预检通过")

        # 2. 结构化上下文 (作家思维：大纲+人物表+伏笔+最近稿子)
        assembler = StructuredAssembler(config)
        ctx = await assembler.assemble(
            chapter_num, beat, characters, world,
            narrator=narrator, narrator_guide="",
            last_emotion=emotion, recent_override=recent,
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

        # 4. 去AI味检测 + 改写 (Phase 3)
        from moliu.deai.detector import DeAIDetector
        from moliu.deai.rewriter import DeAIRewriter
        detector = DeAIDetector()
        l1_report = detector.detect_l1(result.content)
        if l1_report.hard_violations or l1_report.overall_score < 0.8:
            typer.echo(f"去AI味: 评分{l1_report.overall_score:.2f} {len(l1_report.hard_violations)}项违规", nl=False)
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
                    typer.echo(f"\r去AI味: {l1_report.overall_score:.2f}→已改写")
            except Exception:
                typer.echo(f"\r去AI味: {l1_report.overall_score:.2f} (改写跳过)")

        # 5. 质检 (try/except — 质检失败不阻塞章节保存)
        qr = QualityReport()
        try:
            typer.echo("运行质量检查...", nl=False)
            qr = await pipeline.run_quality_checks(result, beat, characters, world, narrator, chapter_num=chapter_num)
            typer.echo(f"\r质检: {qr.consistency_fatal}致命 {qr.consistency_warn}警告 | 读者: {'想继续' if qr.reader_want_next else '不想继续'} | 张力: {qr.tension_score}/10")
        except Exception as e:
            typer.echo(f"\r[WARN] 质检跳过 ({str(e)[:80]}), 正文已生成")

        # 6. 伏笔提醒 (Phase 3)
        from moliu.rules.foreshadow_watch import ForeshadowManager
        fwm = ForeshadowManager(config.resolve_data_dir())
        foreshadow_alerts = fwm.check_alerts(chapter_num)
        if foreshadow_alerts:
            typer.echo(f"伏笔: {len(foreshadow_alerts)} 条提醒")
            for a in foreshadow_alerts[:3]:
                typer.echo(f"  [!] {a[:100]}")

        # 7. 落盘 + 写记忆 + 记节奏
        summary_text = await pipeline.generator._generate_summary_with_llm(result.content, chapter_num)
        clean_summary = summary_text.replace(f"第{chapter_num}章【摘要】", "")

        pipeline.save_meta(chapter_num, result, qr, clean_summary, emotion, characters)
        pipeline.save_to_memory(chapter_num, result, clean_summary, emotion, characters)
        pipeline.save_rhythm_record(chapter_num, result, qr, chapter_type, emotion)

        filepath = config.resolve_output_dir() / Config.chapter_dir_name(chapter_num) / "正文.md"
        return result, filepath

    try:
        result, filepath = asyncio.run(_run())
    except Exception as e:
        typer.echo("\r" + " " * 20 + "\r", nl=False)
        typer.echo(f"[ERROR] 生成失败: {str(e)[:150]}")
        # 提示用户可以使用 retry-segment 命令
        import os
        segment_dir = config.resolve_data_dir() / f"chapter_{chapter_num:03d}" / "segments"
        if segment_dir.exists() and any(segment_dir.iterdir()):
            saved_segments = [f.stem for f in segment_dir.glob("*.txt") if f.stem != "beat"]
            if saved_segments:
                typer.echo(f"[INFO] 已保存的分段: {', '.join(saved_segments)}")
                typer.echo(f"[INFO] 可用 mo retry-segment {chapter_num} 从失败位置继续")
            else:
                # 只有 beat.txt，没有可恢复的分段
                typer.echo(f"[INFO] 无分段已保存，请重新运行 mo write {chapter_num}")
        raise typer.Exit(code=1)

    typer.echo("\r" + " " * 20 + "\r", nl=False)
    typer.echo(f"[OK] 第 {result.chapter_num} 章 生成完成")
    typer.echo(f"   字数: {result.word_count}   Token: {result.tokens_used}")
    typer.echo(f"   开头: {result.content[:80]}...")
    typer.echo(f"   保存: {filepath}")

    # 同步到墨脉图（可选,默认禁用 — 内建关系图谱已覆盖核心功能)
    # 启用方法:在 .env 配置 MO_MOMAITU_* 三项
    if config.is_momaitu_enabled():
        try:
            from moliu.sync.hooks import sync_chapter_artifacts
            asyncio.run(sync_chapter_artifacts(config, chapter_num, result, qr, emotion, characters))
        except Exception as e:
            typer.echo(f"[WARN] 墨脉图同步异常(已自动降级为本地图谱): {e}")


@app.command()
def quickstart(
    prompt: str = typer.Option(
        "", "--prompt", "-p",
        help="一句话描述你想写的小说（留空则交互式输入）",
    ),
    continue_from: str = typer.Option(
        "", "--continue", "-c",
        help="从指定步骤继续（direction/world/characters/narrator），跳过前面的步骤",
    ),
):
    """
    快速开始 — 交互式创建故事方向 + 世界观 + 角色 + 叙述者。
    支持续传模式：检测到已存在的文件时可选择继续或重新生成。
    每个环节 AI 出方案，你来选择和修改。
    """
    config = load_config()
    data_dir = config.resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not prompt:
        prompt = typer.prompt("请一句话描述你想写的小说")

    rollback = QuickstartRollback()

    # 检查是否需要续传
    skip = {"direction": False, "world": False, "characters": False, "narrator": False}
    if continue_from:
        # 命令行指定续传点
        steps = ["direction", "world", "characters", "narrator"]
        try:
            idx = steps.index(continue_from)
            for i in range(idx):
                skip[steps[i]] = True
        except ValueError:
            typer.echo(f"[WARN] 无效的续传点: {continue_from}，忽略此选项")
    else:
        # 自动检测续传
        skip = check_continue(data_dir)

    # 异步执行主流程（避免 asyncio.run 嵌套）
    async def _async_main():
        nonlocal chosen_direction, world, chars

        # ========== Step 1/4: 故事方向 ==========
        if skip.get("direction", False):
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 1/4: 故事方向 [SKIP] <<<")
            typer.echo("=" * 50)
            chosen_direction = (data_dir / "direction.txt").read_text(encoding="utf-8")
            typer.echo("  已加载现有文件")
        else:
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 1/4: 故事方向 <<<")
            typer.echo("AI 出 3 个方向方案，你选一个")
            typer.echo("=" * 50)

            rollback.track(data_dir / "direction.txt")
            chosen_direction = await step_direction(config, prompt, data_dir)

        # ========== Step 2/4: 世界观 ==========
        if skip.get("world", False):
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 2/4: 世界观 [SKIP] <<<")
            typer.echo("=" * 50)
            world = (data_dir / "world" / "world.yaml").read_text(encoding="utf-8")
            typer.echo("  已加载现有文件")
        else:
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 2/4: 世界观 <<<")
            typer.echo("=" * 50)

            rollback.track(data_dir / "world" / "world.yaml")
            world = await step_world(config, chosen_direction, data_dir)

        # ========== Step 3/4: 角色 ==========
        if skip.get("characters", False):
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 3/4: 角色 [SKIP] <<<")
            typer.echo("=" * 50)
            chars = [f.stem for f in (data_dir / "characters").glob("*.yaml")]
            typer.echo(f"  已加载 {len(chars)} 个现有角色")
        else:
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 3/4: 角色 <<<")
            typer.echo("=" * 50)

            chars = await step_characters(config, chosen_direction, world, data_dir, rollback)

        # ========== Step 4/4: 叙述者 ==========
        if skip.get("narrator", False):
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 4/4: 叙述者 [SKIP] <<<")
            typer.echo("=" * 50)
            typer.echo("  已加载现有文件")
        else:
            typer.echo("\n" + "=" * 50)
            typer.echo(">>> Step 4/4: 叙述者风格 <<<")
            typer.echo("=" * 50)

            rollback.track(data_dir / "narrator.md")
            await step_narrator(config, chosen_direction, world, chars, data_dir)

    chosen_direction = ""
    world = ""
    chars = []

    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        typer.echo("\n[!] 用户中断，回滚已写入的文件...")
        rollback.undo()
        typer.echo("[OK] 已清理。可以重新运行 mo quickstart。")
        raise typer.Exit(code=1)

    typer.echo("\n" + "=" * 50)
    typer.echo("创世完成!")
    typer.echo(f"  故事方向: data/direction.txt")
    typer.echo(f"  世界观: data/world/world.yaml")
    typer.echo(f"  角色: data/characters/*.yaml ({len(chars)} 个)")
    typer.echo(f"  叙述者: data/narrator.md")
    typer.echo(f"\n下一步: mo write 1 \"第一章的节拍描述\"")
    typer.echo("=" * 50)

    # 同步到墨脉图（可选,默认禁用 — 内建关系图谱已覆盖核心功能)
    if config.is_momaitu_enabled():
        try:
            from moliu.sync.hooks import sync_quickstart_artifacts
            asyncio.run(sync_quickstart_artifacts(
                config,
                world_yaml_path=data_dir / "world" / "world.yaml",
                characters_dir=data_dir / "characters",
                narrator_md_path=data_dir / "narrator.md",
            ))
        except Exception as e:
            typer.echo(f"[WARN] 墨脉图同步异常(已自动降级为本地图谱): {e}")


@app.command()
def retry_segment(
    chapter_num: int = typer.Argument(..., help="章节号"),
):
    """从分段失败处重试生成章节"""
    config = load_config()
    gateway = DeepSeekGateway(config)
    prompts = PromptManager(config)
    generator = Generator(config, gateway, prompts)

    from moliu.memory.store import MemoryStore
    from moliu.context.assembler import StructuredAssembler
    from moliu.engines.checker import ConsistencyChecker
    from moliu.engines.reader_eval import ReaderEvaluator
    from moliu.rules.rhythm_tracker import RhythmTracker
    from moliu.orchestrator.pipeline import ChapterPipeline, QualityReport
    from moliu.engines.usage import UsageTracker

    memory = MemoryStore(str(config.resolve_data_dir() / "memory_db"))
    retriever = StructuredAssembler(config)
    checker = ConsistencyChecker(gateway)
    reader = ReaderEvaluator(gateway)
    tracker = RhythmTracker(config.resolve_data_dir())
    usage_tracker = UsageTracker(
        config.resolve_data_dir() / "usage_log.jsonl",
        monthly_budget=getattr(config, 'monthly_token_budget', 0),
    )
    gateway.usage_tracker = usage_tracker

    pipeline = ChapterPipeline(
        config, gateway, prompts,
        memory=memory, retriever=retriever,
        checker=checker, reader=reader, tracker=tracker,
    )

    # 检查已保存的分段
    saved_segments = generator._list_saved_segments(chapter_num)
    
    if not saved_segments:
        typer.echo(f"[!] 没有找到第{chapter_num}章的分段数据")
        raise typer.Exit(code=1)
    
    typer.echo(f"[OK] 已找到的分段: {', '.join(saved_segments)}")
    
    # 确定从哪里开始重试
    if "ending" in saved_segments:
        typer.echo("[!] 所有分段都已完成，无需重试")
        raise typer.Exit(code=0)
    elif "middle" in saved_segments:
        resume_from = "ending"
        typer.echo(f"[>] 从 ending 部分继续")
    elif "opening" in saved_segments:
        resume_from = "middle"
        typer.echo(f"[>] 从 middle 部分继续")
    else:
        typer.echo("[!] 没有找到可恢复的分段")
        raise typer.Exit(code=1)
    
    # 加载角色和世界观
    characters = load_characters(config)
    world = load_world(config)
    narrator = load_narrator(config)
    
    if not characters:
        typer.echo("[!] 没有找到角色，请先运行 mo quickstart")
        raise typer.Exit(code=1)
    
    # 从保存的分段中加载原始 beat
    beat = generator._load_beat(chapter_num)
    if not beat:
        beat = f"第{chapter_num}章"
    typer.echo(f"[INFO] 使用节拍: {beat[:30]}..." if len(beat) > 30 else f"[INFO] 使用节拍: {beat}")
    
    # 从保存的分段中加载原始 chapter_type
    original_chapter_type = generator._load_chapter_type(chapter_num)
    typer.echo(f"[INFO] 章节类型: {original_chapter_type}")
    
    # 异步重试函数
    async def _async_retry():
        typer.echo(f"\n[*] 开始重试生成第{chapter_num}章...")
        result = await pipeline.generator.generate_chapter(
            chapter_num=chapter_num,
            beat=beat,
            characters=characters,
            world=world,
            last_emotion="轻松",
            recent_chapters="",
            narrator_card=narrator,
            segmented=True,
            chapter_type=original_chapter_type,
            resume_from=resume_from,
        )

        # 质检 (try/except — 不阻塞)
        qr = QualityReport()
        try:
            qr = await pipeline.run_quality_checks(result, beat, characters, world, narrator, chapter_num=chapter_num)
        except Exception:
            pass

        # 落盘 + 记忆 + 节奏
        summary_text = await pipeline.generator._generate_summary_with_llm(result.content, chapter_num)
        clean_summary = summary_text.replace(f"第{chapter_num}章【摘要】", "")
        pipeline.save_meta(chapter_num, result, qr, clean_summary, "轻松", characters)
        pipeline.save_to_memory(chapter_num, result, clean_summary, "轻松", characters)
        pipeline.save_rhythm_record(chapter_num, result, qr, original_chapter_type, "轻松")

        # 清理临时分段文件
        pipeline.generator._clear_segments(chapter_num)
        return result, config.resolve_output_dir() / Config.chapter_dir_name(chapter_num) / "正文.md"
    
    try:
        result, filepath = asyncio.run(_async_retry())
        typer.echo(f"\n[OK] 第{chapter_num}章生成完成!")
        typer.echo(f"  字数: {result.word_count}")
        typer.echo(f"  保存: {filepath}")
        
    except Exception as e:
        typer.echo(f"\n[!] 生成失败: {str(e)}")
        typer.echo(f"    已保存的分段: {generator._list_saved_segments(chapter_num)}")
        typer.echo(f"    可以再次运行 mo retry-segment {chapter_num} 重试")
        raise typer.Exit(code=1)


@app.command()
def init():
    """初始化项目目录结构"""
    config = load_config()
    data_dir = config.resolve_data_dir()

    dirs = [
        data_dir / "world",
        data_dir / "characters",
        data_dir / "outlines",
        data_dir / "volumes",
        data_dir / "notes",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        typer.echo(f"  [OK] {d.relative_to(config.project_dir)}")

    output_dir = config.resolve_output_dir()
    typer.echo(f"  [OK] {output_dir.relative_to(config.project_dir)}")

    sample_char_path = data_dir / "characters" / "主角.yaml.sample"
    if not sample_char_path.exists():
        sample_char = """# 示例角色人设卡
# 复制此文件并去掉 .sample 后缀即可使用
name: "主角名"
one_line_pitch: "一句话定位这个角色"
speech_profile:
  style: "简短、理性"
  sentence_length: "短句为主"
  tone: "陈述句多，感叹号少"
  common_words: ["行", "嗯"]
  banned_words: ["真的吗", "太好了"]
speech_samples:
  - "\"行。\"（被要求做某事时）"
  - "\"方案有三个。\"（分析问题时）"
core:
  core_desire: "掌控自己的人生"
  surface_desire: "完成系统任务"
  deep_fear: "再次失去在乎的人"
  value_bottom_line: ["不伤及无辜"]
state:
  location: "A市大学城"
  current_goal: "完成第一个系统任务"
  current_emotion: "紧张但冷静"
"""
        sample_char_path.write_text(sample_char, encoding="utf-8")
        typer.echo(f"  [OK] {sample_char_path.relative_to(config.project_dir)} (示例)")

    # 创建示例卷索引
    vol_index_path = data_dir / "volumes" / "index.json"
    if not vol_index_path.exists():
        from moliu.data.schemas import VolumeIndex, VolumePlan
        import json
        sample_index = VolumeIndex(novel_title="")
        with open(vol_index_path, "w", encoding="utf-8") as f:
            json.dump(sample_index.model_dump(), f, ensure_ascii=False, indent=2)
        typer.echo(f"  [OK] {vol_index_path.relative_to(config.project_dir)} (示例)")

    typer.echo("\n--- 下一步 ---")
    typer.echo("  1. 设置 MO_DEEPSEEK_API_KEY 环境变量或在 .env 文件中")
    typer.echo("  2. 编辑 data/world/world.yaml")
    typer.echo("  3. 编辑 data/characters/*.yaml")
    typer.echo("  4. 规划卷结构: mo volume create --name \"卷一名\" --range 1-30")
    typer.echo("  5. 查看卷: mo volume list")
    typer.echo('  6. 生成章节: mo write 1 "主角获得系统，完成第一个任务"')
    typer.echo("  7. 补全元数据: mo backfill 1-50")
    typer.echo("  或使用快速开始: mo quickstart -p \"你的小说描述\"")


@app.command()
def check(
    chapter_num: int = typer.Argument(..., help="要检查的章节号"),
    characters_filter: str = typer.Option(
        "", "--characters", "-c",
        help="出场角色名，逗号分隔",
    ),
):
    """对已生成的章节运行一致性检查 + 读者体验评估"""
    config = load_config()

    output_dir = config.resolve_output_dir()
    chapter_path = output_dir / Config.chapter_dir_name(chapter_num) / "正文.md"
    if not chapter_path.exists():
        typer.echo(f"[ERROR] 第{chapter_num}章不存在")
        raise typer.Exit(code=1)

    content = chapter_path.read_text(encoding="utf-8")
    all_characters = load_characters(config)
    if characters_filter:
        names = [n.strip() for n in characters_filter.split(",")]
        characters = [c for c in all_characters if c.name in names]
    else:
        characters = all_characters

    world = load_world(config)
    narrator = load_narrator(config)

    if not world:
        typer.echo("[ERROR] 世界观未创建")
        raise typer.Exit(code=1)

    from moliu.engines.checker import ConsistencyChecker
    from moliu.engines.reader_eval import ReaderEvaluator
    from moliu.rules.rhythm_tracker import TensionScorer

    async def _run():
        gw = DeepSeekGateway(config)
        try:
            checker = ConsistencyChecker(gw)
            reader = ReaderEvaluator(gw)

            typer.echo(f"=== 第{chapter_num}章 质检 ===")
            typer.echo("运行一致性检查...", nl=False)
            report = await checker.check(content, characters, world, narrator)
            typer.echo(f"\r一致性: {report.fatal_count}致命 {report.warning_count}警告 {report.info_count}提示")

            typer.echo("运行读者评估...", nl=False)
            fb = await reader.evaluate(content)
            typer.echo(f"\r读者: {'想继续' if fb.want_next else '不想继续'}"
                       f"{' (感觉重复)' if fb.feels_repetitive else ''}")

            tension = TensionScorer.score(content)
            typer.echo(f"张力评分: {tension}/10")

            # 保存报告
            report_path = output_dir / Config.chapter_dir_name(chapter_num) / "质量报告.md"
            lines = [
                f"# 第{chapter_num}章 质检报告",
                "",
                "## 一致性检查",
                report.to_text(),
                "",
                "## 读者评估",
                fb.summary(),
                "",
                f"## 张力评分: {tension}/10",
                "",
                "## 读者原始反馈",
                fb.raw_feedback,
            ]
            report_path.write_text("\n\n".join(lines), encoding="utf-8")
            typer.echo(f"报告已保存: {report_path}")

            if report.fatal_count > 0:
                typer.echo("\n[WARN] 发现致命问题，建议修复后再继续")
            else:
                typer.echo("\n[OK] 质检通过")
        finally:
            await gw.close()
    asyncio.run(_run())


@app.command()
def usage():
    """查看 Token 用量统计"""
    config = load_config()
    from moliu.engines.usage import UsageTracker

    tracker = UsageTracker(
        config.resolve_data_dir() / "usage_log.jsonl",
        monthly_budget=getattr(config, 'monthly_token_budget', 0),
    )

    typer.echo("=== Token 用量统计 ===")
    typer.echo(f"今日: {tracker.today():,}")
    typer.echo(f"本周: {tracker.this_week():,}")
    typer.echo(f"本月: {tracker.this_month():,}")
    typer.echo(f"预算: {tracker.budget_status()}")
    typer.echo(f"平均每章: {tracker.average_per_chapter():.0f} tokens")

    by_ch = tracker.by_chapter()
    if by_ch:
        typer.echo("\n每章用量:")
        for ch in sorted(by_ch):
            typer.echo(f"  第{ch}章: {by_ch[ch]:,}")


# ========== 元数据回填 ==========

@app.command()
def backfill(
    chapter_range: str = typer.Argument(
        ..., help="章节范围，如 '1-50' 或 'all'",
    ),
    fields: str = typer.Option(
        "title,emotion,events",
        "--fields", "-f",
        help="要回填的字段，逗号分隔: title,emotion,events",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="仅扫描显示缺失情况，不实际调用 LLM",
    ),
    concurrency: int = typer.Option(
        3, "--concurrency", "-c",
        help="并发数（同时调用 LLM 的章节数）",
    ),
):
    """批量回填章节元数据（标题/情绪/关键事件）

    用法:
        mo backfill 1-50                    # 回填第1-50章
        mo backfill 51-125 --fields title   # 仅补标题
        mo backfill all --dry-run           # 仅查看缺失情况
    """
    import asyncio
    from moliu.engines.backfill import MetadataBackfiller, scan_missing_metadata, print_missing_summary

    config = load_config()
    output_dir = config.resolve_output_dir()

    # 解析章节范围
    chapter_range = chapter_range.strip()
    if chapter_range == "all":
        existing = sorted(output_dir.iterdir())
        nums = []
        for d in existing:
            if not d.is_dir():
                continue
            ch = Config.parse_chapter_num(d.name)
            if ch is not None:
                nums.append(ch)
        if not nums:
            typer.echo("[!] 没有找到任何章节")
            raise typer.Exit(code=1)
        start, end = min(nums), max(nums)
    elif "-" in chapter_range:
        parts = chapter_range.split("-")
        start, end = int(parts[0]), int(parts[1])
    else:
        start = end = int(chapter_range)

    # 解析字段
    field_list = [f.strip() for f in fields.split(",") if f.strip()]

    # 先扫描
    typer.echo(f"扫描第 {start}-{end} 章元数据...")
    scan_results = scan_missing_metadata(output_dir)
    filtered = [r for r in scan_results if start <= r["chapter_num"] <= end]
    print_missing_summary(filtered)

    if dry_run:
        return

    # 确认
    typer.echo("")
    typer.echo(f"准备回填字段: {', '.join(field_list)}")
    confirmed = typer.confirm("开始回填?", default=True)
    if not confirmed:
        typer.echo("已取消")
        raise typer.Exit(code=0)

    # 执行回填
    backfiller = MetadataBackfiller(config)

    def _progress(ch: int, result: dict):
        if result:
            fields_done = [k for k in result.keys() if result[k]]
            typer.echo(f"  [OK] 第{ch}章: {', '.join(fields_done)}")
        else:
            typer.echo(f"  [--] 第{ch}章: 无变化或跳过")

    typer.echo(f"\n开始回填（并发: {concurrency}）...")
    asyncio.run(backfiller.backfill_range(start, end, field_list, concurrency, _progress))

    # 回填后再次扫描
    typer.echo("\n回填完成，重新扫描确认...")
    scan_results = scan_missing_metadata(output_dir)
    filtered = [r for r in scan_results if start <= r["chapter_num"] <= end]
    print_missing_summary(filtered)


# ========== API 服务 ==========

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    reload: bool = typer.Option(False, "--reload", "-r", help="热重载（开发用）"),
):
    """启动墨流 API 服务器（FastAPI）

    启动后，浏览器访问 http://localhost:8000 进入创作工作台。
    """
    import uvicorn
    typer.echo(f"[OK] 启动墨流 API 服务器: http://{host}:{port}")
    typer.echo(f"  创作工作台: http://localhost:{port}/  (主界面)")
    typer.echo(f"  API 文档: http://localhost:{port}/docs")
    if reload:
        typer.echo("  热重载模式: 开启")
    uvicorn.run("moliu.api:app", host=host, port=port, reload=reload)


# ========== 卷管理 ==========

@app.command()
def volume(
    action: str = typer.Argument(
        ..., help="操作: list / create / update / assign",
    ),
    volume_id: int = typer.Option(
        0, "--id", "-i", help="卷 ID（create 时可选，update/assign 时必填）",
    ),
    name: str = typer.Option(
        "", "--name", "-n", help="卷名称",
    ),
    subtitle: str = typer.Option(
        "", "--subtitle", "-s", help="卷副标题",
    ),
    chapter_range: str = typer.Option(
        "", "--range", "-r", help="章节范围，如 '1-30'",
    ),
    summary: str = typer.Option(
        "", "--summary", "-m", help="卷摘要",
    ),
):
    """卷管理 — 查看、创建、更新卷规划

    用法:
        mo volume list                          # 查看所有卷
        mo volume create --name "卷名" --range 1-30  # 创建新卷
        mo volume update --id 1 --name "新名称"     # 更新卷
        mo volume assign --id 1 --range 1-30        # 重新分配章节范围
    """
    import json
    from moliu.data.schemas import VolumeIndex, VolumePlan

    config = load_config()
    data_dir = config.resolve_data_dir()
    vol_dir = data_dir / "volumes"
    vol_dir.mkdir(parents=True, exist_ok=True)
    index_path = vol_dir / "index.json"

    # 加载或创建索引
    if index_path.exists():
        vol_index = VolumeIndex.from_json(index_path)
    else:
        vol_index = VolumeIndex()
        vol_index.to_json(index_path)

    if action == "list":
        if not vol_index.volumes:
            typer.echo("暂无卷规划。使用 'mo volume create' 创建。")
        else:
            typer.echo(f"=== 卷列表 ({vol_index.novel_title or '未命名小说'}) ===")
            for v in vol_index.volumes:
                ch_range = f"第{v.chapter_start}-{v.chapter_end}章" if v.chapter_end else "未定义范围"
                status_icon = "✅" if v.status == "completed" else "📝" if v.status == "active" else "📋"
                typer.echo(f"  {status_icon} 卷{v.id}: {v.name or '(未命名)'}")
                typer.echo(f"    范围: {ch_range} | 状态: {v.status}")
                if v.subtitle:
                    typer.echo(f"    副标题: {v.subtitle}")
                if v.summary:
                    typer.echo(f"    摘要: {v.summary[:60]}...")
                if v.arcs:
                    typer.echo(f"    故事弧: {len(v.arcs)} 个")
                typer.echo("")

    elif action == "create":
        # 自动生成 ID
        if volume_id <= 0:
            volume_id = max((v.id for v in vol_index.volumes), default=0) + 1

        if not name:
            name = typer.prompt("卷名称")
        if not chapter_range:
            chapter_range = typer.prompt("章节范围（如 1-30）")
        if not summary:
            summary = typer.prompt("卷摘要（可选）", default="")

        parts = chapter_range.split("-")
        ch_start = int(parts[0])
        ch_end = int(parts[1]) if len(parts) > 1 else ch_start

        new_vol = VolumePlan(
            id=volume_id,
            name=name,
            subtitle=subtitle,
            chapter_start=ch_start,
            chapter_end=ch_end,
            summary=summary,
            status="planned",
        )
        vol_index.volumes.append(new_vol)
        # 按 ID 排序
        vol_index.volumes.sort(key=lambda v: v.id)
        vol_index.to_json(index_path)
        typer.echo(f"[OK] 卷 {volume_id}「{name}」已创建（第{ch_start}-{ch_end}章）")

    elif action == "update":
        if volume_id <= 0:
            typer.echo("[!] 请指定卷 ID: --id 1")
            raise typer.Exit(code=1)

        target = next((v for v in vol_index.volumes if v.id == volume_id), None)
        if not target:
            typer.echo(f"[!] 卷 {volume_id} 不存在")
            raise typer.Exit(code=1)

        if name:
            target.name = name
        if subtitle:
            target.subtitle = subtitle
        if summary:
            target.summary = summary
        if chapter_range:
            parts = chapter_range.split("-")
            target.chapter_start = int(parts[0])
            target.chapter_end = int(parts[1]) if len(parts) > 1 else target.chapter_end

        vol_index.to_json(index_path)
        typer.echo(f"[OK] 卷 {volume_id} 已更新")

    elif action == "assign":
        if volume_id <= 0:
            typer.echo("[!] 请指定卷 ID: --id 1")
            raise typer.Exit(code=1)
        if not chapter_range:
            typer.echo("[!] 请指定章节范围: --range 1-30")
            raise typer.Exit(code=1)

        target = next((v for v in vol_index.volumes if v.id == volume_id), None)
        if not target:
            typer.echo(f"[!] 卷 {volume_id} 不存在")
            raise typer.Exit(code=1)

        parts = chapter_range.split("-")
        target.chapter_start = int(parts[0])
        target.chapter_end = int(parts[1]) if len(parts) > 1 else target.chapter_end

        vol_index.to_json(index_path)
        typer.echo(f"[OK] 卷 {volume_id} 章节范围已更新为第{target.chapter_start}-{target.chapter_end}章")

    else:
        typer.echo(f"[!] 未知操作: {action}，支持: list / create / update / assign")


if __name__ == "__main__":
    app()
