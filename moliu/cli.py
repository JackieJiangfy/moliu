"""墨流 CLI — 入口"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import typer
import yaml as _yaml

from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.generator import Generator
from moliu.prompts.manager import PromptManager

app = typer.Typer(
    name="mo",
    help="墨流 - AI 小说创作工作流引擎",
    no_args_is_help=True,
)


def _load_config() -> Config:
    try:
        return Config()
    except Exception as e:
        typer.echo(f"[ERROR] 配置加载失败: {e}")
        typer.echo("请确保设置了 MO_DEEPSEEK_API_KEY 环境变量或 .env 文件")
        raise typer.Exit(code=1)


def _load_characters(config: Config) -> list[CharacterCard]:
    chars_dir = config.resolve_data_dir() / "characters"
    if not chars_dir.exists():
        return []
    characters = []
    for f in sorted(chars_dir.glob("*.yaml")):
        try:
            characters.append(CharacterCard.from_yaml(f))
        except Exception as e:
            typer.echo(f"[WARN] 跳过 {f.name}: {e}")
    return characters


def _load_world(config: Config) -> WorldSetting | None:
    world_path = config.resolve_data_dir() / "world" / "world.yaml"
    if not world_path.exists():
        return None
    return WorldSetting.from_yaml(world_path)


def _load_narrator(config: Config) -> str:
    narrator_path = config.resolve_data_dir() / "narrator.md"
    if not narrator_path.exists():
        return ""
    return narrator_path.read_text(encoding="utf-8")


# === commands ===

@app.command()
def status():
    """查看项目状态: 角色数、已有章节数、世界观概况"""
    config = _load_config()
    characters = _load_characters(config)
    world = _load_world(config)
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
    config = _load_config()

    all_characters = _load_characters(config)
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

    world = _load_world(config)
    if not world:
        typer.echo("[ERROR] 没有找到世界观文件。请先在 data/world/world.yaml 创建世界观")
        raise typer.Exit(code=1)

    narrator = _load_narrator(config)

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
            narrator_guide=narrator,
            temperature=temperature,
        )
        filepath = generator.save_chapter(result)
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
):
    """
    快速开始 — 交互式创建故事方向 + 世界观 + 角色 + 叙述者。
    每个环节 AI 出方案，你来选择和修改。
    """
    config = _load_config()
    data_dir = config.resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not prompt:
        prompt = typer.prompt("请一句话描述你想写的小说")

    rollback = _QuickstartRollback()

    try:
        # ========== Step 1/4: 故事方向 ==========
        typer.echo("\n" + "=" * 50)
        typer.echo(">>> Step 1/4: 故事方向 <<<")
        typer.echo("AI 出 3 个方向方案，你选一个")
        typer.echo("=" * 50)

        rollback.track(data_dir / "direction.txt")
        chosen_direction = _step_direction(config, prompt, data_dir)

        # ========== Step 2/4: 世界观 ==========
        typer.echo("\n" + "=" * 50)
        typer.echo(">>> Step 2/4: 世界观 <<<")
        typer.echo("=" * 50)

        rollback.track(data_dir / "world" / "world.yaml")
        world = _step_world(config, chosen_direction, data_dir)

        # ========== Step 3/4: 角色 ==========
        typer.echo("\n" + "=" * 50)
        typer.echo(">>> Step 3/4: 角色 <<<")
        typer.echo("=" * 50)

        chars = _step_characters(config, chosen_direction, world, data_dir, rollback)

        # ========== Step 4/4: 叙述者 ==========
        typer.echo("\n" + "=" * 50)
        typer.echo(">>> Step 4/4: 叙述者风格 <<<")
        typer.echo("=" * 50)

        rollback.track(data_dir / "narrator.md")
        _step_narrator(config, chosen_direction, world, chars, data_dir)

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


# ========== Step 辅助函数 ==========

def _step_direction(config: Config, prompt: str, data_dir: Path) -> str:
    """AI 出 3 个故事方向 → 人选择 → 返回选中的方向"""
    system_prompt = """你是资深网文策划。用户给了模糊的方向，你需要帮 ta 细化成 3 个具体可操作的故事方案。

每个方案必须是一个完整的故事概念，包含以下要素：

【方案名】：一句话标题，用于区分（如"社恐程序员逆袭"）
【一句话梗概】：像番茄小说的简介一样，一句话讲清楚主角、金手指、核心冲突
【主角画像】：主角是什么样的人，有什么性格亮点和缺点
【金手指/核心设定】：故事的能力体系或核心玩法的独特之处
【爽点机制】：这本书凭什么让读者爽——打脸？升级？赚钱？智斗？反转？
【开篇方向】：前 10 章大致的发展方向
【文风建议】：这本书适合的叙事风格（轻松吐槽 / 紧张悬疑 / 热血少年 / 冷静智斗等）

3 个方案要有明显区分度——不要 3 个都是同一类型换个名字。覆盖不同的爽点类型和文风。
用 === 分隔 3 个方案。"""

    user_prompt = f"用户的模糊想法: {prompt}\n\n请生成 3 个不同的故事方案。确保方案之间有明显的类型差异。"

    directions_text = _generate_with_retry(config, system_prompt, user_prompt)

    # 按 === 拆分成 3 个方案
    blocks = re.split(r"\n\s*={3,}\s*\n", directions_text)
    blocks = [b.strip() for b in blocks if len(b.strip()) > 50]

    if len(blocks) < 2:
        typer.echo("[WARN] AI 没有正确生成 3 个方案，使用原始输出")
        typer.echo(directions_text[:2000])
        return prompt + "\n\n" + directions_text

    typer.echo(f"\nAI 为你设计了 {len(blocks)} 个故事方案:\n")
    for i, block in enumerate(blocks):
        typer.echo(f"{'─' * 40}")
        typer.echo(f"  方案 {i + 1}")
        typer.echo(f"{'─' * 40}")
        typer.echo(block[:500] + ("..." if len(block) > 500 else ""))
        typer.echo()

    while True:
        choice = typer.prompt(
            f"选一个方案 (1-{len(blocks)}) / [redo] 全部重来 / [custom] 输入自定义方向",
            default="1",
        ).strip().lower()

        if choice == "redo":
            directions_text = _generate_with_retry(config, system_prompt, user_prompt)
            blocks = [b.strip() for b in re.split(r"\n\s*={3,}\s*\n", directions_text) if len(b.strip()) > 50]
            typer.echo("\n--- 重新生成 ---\n")
            for i, block in enumerate(blocks):
                typer.echo(f"{'─' * 40}")
                typer.echo(f"  方案 {i + 1}")
                typer.echo(f"{'─' * 40}")
                typer.echo(block[:500] + ("..." if len(block) > 500 else ""))
                typer.echo()
        elif choice == "custom":
            custom = typer.prompt("请输入你的想法（可以混合 AI 给的方案）")
            return f"原始想法: {prompt}\n\n用户选择的自定义方向:\n{custom}"
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(blocks):
                    selected = blocks[idx]
                    typer.echo(f"\n你选择了方案 {idx + 1}")
                    # 保存方向
                    (data_dir / "direction.txt").write_text(selected, encoding="utf-8")
                    typer.echo(f"  -> 已保存: data/direction.txt")
                    return selected
                else:
                    typer.echo(f"[WARN] 请输入 1-{len(blocks)}")
            except ValueError:
                typer.echo(f"[WARN] 请输入数字 1-{len(blocks)}，或 redo / custom")


def _step_world(config: Config, prompt: str, data_dir) -> str:
    """生成世界观 → 展示 → 人确认/修改"""
    system_prompt = """你是资深网文设定师。根据用户的一句话描述，生成完整的世界观设定。

输出严格的 YAML 格式:
era: "时代背景"
core_rules:
  - "核心规则1"
  - "核心规则2"
power_system: "力量体系简述"
faction_summary: "势力分布简述"
key_constraints:
  - "硬约束1"
  - "硬约束2"
narrative_style: "叙事基调"

要求:
- 规则清晰具体，不要空泛
- 硬约束是 AI 绝对不能越过的红线
- 叙事基调一句话概括（如"轻松吐槽风"、"紧张悬疑风"）"""

    world_yaml = _generate_with_retry(config, system_prompt, prompt)
    typer.echo("\n--- 世界观草案 ---\n")
    typer.echo(world_yaml)

    while True:
        choice = typer.prompt(
            "\n[OK] 确认 / [edit] 输入修改意见 / [redo] 重新生成",
            default="ok",
        ).strip().lower()

        if choice in ("", "ok", "y", "yes"):
            break
        elif choice == "redo":
            world_yaml = _generate_with_retry(config, system_prompt, prompt)
            typer.echo("\n--- 重新生成 ---\n")
            typer.echo(world_yaml)
        else:
            # 用户输入修改意见
            revision_prompt = f"原设定:\n{world_yaml}\n\n修改意见: {choice}\n\n请根据修改意见调整世界观设定，输出完整的 YAML。"
            world_yaml = _generate_with_retry(config, system_prompt, revision_prompt)
            typer.echo("\n--- 修改后 ---\n")
            typer.echo(world_yaml)

    world_path = data_dir / "world" / "world.yaml"
    world_path.parent.mkdir(parents=True, exist_ok=True)

    # 校验 YAML：失败则要求修正，不写坏文件
    while True:
        try:
            data = _yaml.safe_load(world_yaml)
            if not isinstance(data, dict):
                raise ValueError("YAML 不是 dict")
            WorldSetting(**data)
            break
        except Exception as e:
            typer.echo(f"[WARN] 世界观 YAML 校验失败: {e}")
            typer.echo("[WARN] 请 redo 重新生成，或 edit 修正格式")
            choice = typer.prompt(
                "[redo] 重新生成 / [edit] 输入修改意见",
                default="redo",
            ).strip().lower()
            if choice == "redo":
                world_yaml = _generate_with_retry(config, system_prompt, prompt)
                typer.echo("\n--- 重新生成 ---\n")
                typer.echo(world_yaml)
            else:
                revision_prompt = f"原设定（YAML 格式错误）:\n{world_yaml}\n\n修改意见: {choice}\n\n请输出合法的 YAML。"
                world_yaml = _generate_with_retry(config, system_prompt, revision_prompt)
                typer.echo("\n--- 修正后 ---\n")
                typer.echo(world_yaml)

    world_path.write_text(world_yaml, encoding="utf-8")
    typer.echo(f"  -> 已保存: data/world/world.yaml")
    return world_yaml


def _step_characters(config: Config, prompt: str, world: str, data_dir, rollback: _QuickstartRollback | None = None) -> list[str]:
    """生成角色 → 展示 → 人确认/逐个修改"""
    system_prompt = """你是资深网文人设师。根据世界观和故事方向，生成 3 个初始角色的人设卡。

输出 3 个角色，每个用 --- 分隔。每个角色严格按以下 YAML 格式:

name: "角色名"
one_line_pitch: "一句话定位这个角色"
speech_profile:
  style: "说话风格简述"
  sentence_length: "短句为主/中等长度/长句多"
  tone: "语气特点"
  common_words: ["常用词1", "常用词2"]
  banned_words: ["禁用词1", "禁用词2"]
speech_samples:
  - "\"行。\"（被要求做任务时）"
  - "\"分析过了。\"（遇到问题时）"
inner_voice_style: "内心戏特色（如：代码注释式自言自语）"
core:
  core_desire: "核心欲望（他/她真正想要什么）"
  surface_desire: "表层欲望（当前在追求什么）"
  deep_fear: "深层恐惧（最怕什么）"
  value_bottom_line: ["底线1", "底线2"]
backstory_summary: "背景故事简述"
backstory_impact: "背景对当前行为的影响"
state:
  location: "当前所在地"
  current_goal: "当前目标"
  current_emotion: "当前情绪基调"

要求:
- 3 个角色性格要有明显区分度
- 主角要有缺点，不要太完美
- 每个角色至少 2 条说话样本
- 禁用词是 AI 生成时绝对不能用的词"""

    user_prompt = f"故事方向: {prompt}\n\n世界观:\n{world}\n\n请生成 3 个初始角色的人设卡。"

    chars_text = _generate_with_retry(config, system_prompt, user_prompt)
    blocks = _split_character_blocks(chars_text)

    typer.echo(f"\n--- 角色方案 ({len(blocks)} 个) ---\n")
    for i, block in enumerate(blocks):
        name = "?"
        m = re.search(r'name:\s*"?([^"\n]+)"?', block)
        if m:
            name = m.group(1).strip()
        typer.echo(f"--- 角色 {i + 1}: {name} ---")
        typer.echo(block[:300] + ("..." if len(block) > 300 else ""))
        typer.echo()

    while True:
        choice = typer.prompt(
            "[OK] 全部确认 / [edit N] 修改第N个 (如 edit 1) / [redo] 全部重来",
            default="ok",
        ).strip().lower()

        if choice in ("", "ok", "y", "yes"):
            break
        elif choice == "redo":
            chars_text = _generate_with_retry(config, system_prompt, user_prompt)
            blocks = _split_character_blocks(chars_text)
            typer.echo("\n--- 重新生成 ---\n")
            for i, block in enumerate(blocks):
                name = "?"
                m = re.search(r'name:\s*"?([^"\n]+)"?', block)
                if m:
                    name = m.group(1).strip()
                typer.echo(f"--- 角色 {i + 1}: {name} ---")
                typer.echo(block[:300] + ("..." if len(block) > 300 else ""))
                typer.echo()
        elif choice.startswith("edit"):
            try:
                idx = int(choice.replace("edit", "").strip()) - 1
                if 0 <= idx < len(blocks):
                    feedback = typer.prompt(f"修改意见（针对角色 {idx + 1}）")
                    rev_prompt = f"原角色:\n{blocks[idx]}\n\n修改意见: {feedback}\n\n请修改这个角色的人设卡，输出完整 YAML。"
                    new_block = _generate_with_retry(config, system_prompt, rev_prompt)
                    blocks[idx] = new_block
                    name = "?"
                    m = re.search(r'name:\s*"?([^"\n]+)"?', new_block)
                    if m:
                        name = m.group(1).strip()
                    typer.echo(f"\n--- 修改后的角色 {idx + 1}: {name} ---")
                    typer.echo(new_block[:300] + ("..." if len(new_block) > 300 else ""))
                else:
                    typer.echo(f"[WARN] 角色编号 {idx + 1} 超出范围 (1-{len(blocks)})")
            except ValueError:
                typer.echo("[WARN] 格式: edit 1 / edit 2 / edit 3")

    # 校验并保存
    chars_dir = data_dir / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)
    saved_names = []
    for block in blocks:
        name = _try_validate_character(block)
        if name is None:
            typer.echo("[WARN] 角色 YAML 格式校验失败，已跳过")
            continue
        saved_names.append(name)
        char_path = chars_dir / f"{name}.yaml"
        if rollback is not None:
            rollback.track(char_path)
        char_path.write_text(block.strip(), encoding="utf-8")
        typer.echo(f"  -> 已保存: data/characters/{name}.yaml")

    return saved_names


def _step_narrator(config: Config, prompt: str, world: str, chars: list[str], data_dir) -> str:
    """生成叙述者风格 → 展示 → 人确认/修改"""
    system_prompt = """你是资深网文编辑。根据世界观和角色设定，为小说设计叙述者的叙事风格。

输出 Markdown 格式:

## 叙述者定位
一句话概括叙事者的身份和语气（如"一个冷眼旁观但偶尔毒舌的损友"）

## 日常语气
轻松场景下的叙述风格

## 高潮语气
紧张/打脸/爆发的叙述风格

## 情绪戏语气
悲伤/感动/沉重的叙述风格

## 句式特征
- 特征1
- 特征2

## 禁用套话
- 套话1
- 套话2

## 风格样本
### 样本: 日常
(写一段 100 字左右的日常场景叙述)

### 样本: 高潮
(写一段 100 字左右的高潮场景叙述)

要求:
- 风格要适配都市系统爽文
- 禁用套话要具体，不是泛泛的"避免AI风"
- 风格样本要展示不同的语气切换"""

    user_prompt = f"故事: {prompt}\n\n角色: {', '.join(chars)}\n\n请为这部小说设计叙述者风格。"

    narrator_md = _generate_with_retry(config, system_prompt, user_prompt)
    typer.echo("\n--- 叙述者风格草案 ---\n")
    typer.echo(narrator_md)

    while True:
        choice = typer.prompt(
            "\n[OK] 确认 / [edit] 输入修改意见 / [redo] 重新生成",
            default="ok",
        ).strip().lower()

        if choice in ("", "ok", "y", "yes"):
            break
        elif choice == "redo":
            narrator_md = _generate_with_retry(config, system_prompt, user_prompt)
            typer.echo("\n--- 重新生成 ---\n")
            typer.echo(narrator_md)
        else:
            rev_prompt = f"原风格:\n{narrator_md}\n\n修改意见: {choice}\n\n请根据修改意见调整叙述者风格，输出完整 Markdown。"
            narrator_md = _generate_with_retry(config, system_prompt, rev_prompt)
            typer.echo("\n--- 修改后 ---\n")
            typer.echo(narrator_md)

    narrator_path = data_dir / "narrator.md"
    narrator_path.write_text(narrator_md, encoding="utf-8")
    typer.echo(f"  -> 已保存: data/narrator.md")
    return narrator_md


def _generate_with_retry(config: Config, system_prompt: str, user_prompt: str) -> str:
    """生成文本。每次调用创建独立的 gateway，避免 AsyncClient 跨事件循环崩溃。"""
    async def _run():
        gw = DeepSeekGateway(config)
        try:
            content, _ = await gw.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=4096,
            )
            return content
        finally:
            await gw.close()
    return asyncio.run(_run())


@app.command()
def init():
    """初始化项目目录结构"""
    config = _load_config()
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


# === 回滚机制 ===

class _QuickstartRollback:
    """跟踪 quickstart 写入的文件，失败时只回滚本次变更"""

    def __init__(self):
        self._tracked: dict[Path, str | None] = {}  # path → original content (None = new file)

    def track(self, path: Path) -> None:
        """写入前调用：记录文件是否存在，存在则备份原内容"""
        if path.exists():
            self._tracked[path] = path.read_text(encoding="utf-8")
        else:
            self._tracked[path] = None

    def undo(self) -> None:
        """回滚：新文件删除，覆盖的文件恢复原内容"""
        for path, original in self._tracked.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(original, encoding="utf-8")
            except OSError:
                pass
        self._tracked.clear()


# === 辅助函数 ===

def _try_validate_character(block: str) -> str | None:
    """尝试将 YAML 文本解析为 CharacterCard，成功返回角色名，失败返回 None"""
    from moliu.data.schemas import CharacterCard as _CC
    try:
        data = _yaml.safe_load(block)
        if not isinstance(data, dict):
            return None
        card = _CC(**data)
        return card.name
    except Exception:
        return None


def _split_character_blocks(text: str) -> list[str]:
    """按 --- 分隔符拆分角色 YAML 块"""
    blocks = re.split(r"\n---\n", text)
    return [b.strip() for b in blocks if b.strip()]


if __name__ == "__main__":
    app()
