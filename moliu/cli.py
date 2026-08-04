"""墨流 CLI — 入口"""

import asyncio
from pathlib import Path

import typer

from moliu.cli.quickstart import check_continue, step_characters, step_direction, step_narrator, step_world
from moliu.cli.utils import QuickstartRollback, load_characters, load_config, load_narrator, load_world
from moliu.engines.generator import Generator
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager

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
    existing_chapters = sorted(output_dir.glob("第*章"))

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
        generator = Generator(config, gateway, prompts)
        result = await generator.generate_chapter(
            chapter_num=chapter_num,
            beat=beat,
            characters=characters,
            world=world,
            last_emotion=emotion,
            recent_chapters=recent,
            narrator_card=narrator,
            temperature=temperature,
        )
        filepath = generator.save_chapter(result, characters=characters)
        return result, filepath

    result, filepath = asyncio.run(_run())

    typer.echo("\r" + " " * 20 + "\r", nl=False)
    typer.echo(f"[OK] 第 {result.chapter_num} 章 生成完成")
    typer.echo(f"   字数: {result.word_count}   Token: {result.tokens_used}")
    typer.echo(f"   开头: {result.content[:80]}...")
    typer.echo(f"   保存: {filepath}")


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

    try:
        # ========== Step 1/4: 故事方向 ==========
        chosen_direction = ""
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
            chosen_direction = asyncio.run(step_direction(config, prompt, data_dir))

        # ========== Step 2/4: 世界观 ==========
        world = ""
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
            world = asyncio.run(step_world(config, chosen_direction, data_dir))

        # ========== Step 3/4: 角色 ==========
        chars = []
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

            chars = asyncio.run(step_characters(config, chosen_direction, world, data_dir, rollback))

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
            asyncio.run(step_narrator(config, chosen_direction, world, chars, data_dir))

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


@app.command()
def init():
    """初始化项目目录结构"""
    config = load_config()
    data_dir = config.resolve_data_dir()

    dirs = [
        data_dir / "world",
        data_dir / "characters",
        data_dir / "outlines",
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

    typer.echo("\n--- 下一步 ---")
    typer.echo("  1. 设置 MO_DEEPSEEK_API_KEY 环境变量或在 .env 文件中")
    typer.echo("  2. 编辑 data/world/world.yaml")
    typer.echo("  3. 编辑 data/characters/*.yaml")
    typer.echo('  4. 运行: mo write 1 "主角获得系统，完成第一个任务"')
    typer.echo("  或使用快速开始: mo quickstart -p \"你的小说描述\"")


if __name__ == "__main__":
    app()
