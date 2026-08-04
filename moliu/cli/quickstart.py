"""quickstart 命令 - 交互式创建故事"""

import asyncio
import re
from pathlib import Path
from typing import Optional

import typer

from moliu.config import Config
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager

from .utils import QuickstartRollback, split_character_blocks, try_validate_character


async def generate_with_retry(
    config: Config,
    template_name: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """使用模板生成文本"""
    prompts = PromptManager(config)
    system_prompt = prompts.render(f"{template_name}.j2")

    gw = DeepSeekGateway(config)
    try:
        content, _ = await gw.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content
    finally:
        await gw.close()


def run_generate_with_retry(config: Config, template_name: str, user_prompt: str) -> str:
    """同步包装的生成函数"""
    return asyncio.run(generate_with_retry(config, template_name, user_prompt))


def check_continue(data_dir: Path) -> dict[str, bool]:
    """
    检查 data/ 目录中已存在的文件，询问用户是否跳过或重新生成

    Returns:
        字典，key 为步骤名，value 为是否跳过 (True=跳过，使用现有文件)
    """
    typer.echo("\n=== 检测到已存在的文件 ===")
    
    checks = {
        "direction": (data_dir / "direction.txt").exists(),
        "world": (data_dir / "world" / "world.yaml").exists(),
        "characters": len(list((data_dir / "characters").glob("*.yaml"))) > 0 if (data_dir / "characters").exists() else False,
        "narrator": (data_dir / "narrator.md").exists(),
    }
    
    has_existing = any(checks.values())
    
    if not has_existing:
        typer.echo("  无现有文件，将从头开始")
        return {k: False for k in checks}
    
    for key, exists in checks.items():
        if exists:
            typer.echo(f"  - [EXISTS] {_get_step_description(key)}")
    
    # 询问用户是否继续
    while True:
        choice = typer.prompt(
            "\n[continue] 从缺失的步骤继续 / [restart] 全部重新生成 / [select] 逐个选择",
            default="continue"
        ).strip().lower()
        
        if choice == "continue":
            # 跳过已存在的，继续缺失的
            return checks
        elif choice == "restart":
            # 全部重新生成
            return {k: False for k in checks}
        elif choice == "select":
            # 逐个选择
            result = {}
            for key, exists in checks.items():
                if exists:
                    while True:
                        opt = typer.prompt(
                            f"  {_get_step_description(key)}: [skip] 保留 / [regenerate] 重新生成",
                            default="skip"
                        ).strip().lower()
                        if opt in ("skip", "s"):
                            result[key] = True
                            break
                        elif opt in ("regenerate", "r"):
                            result[key] = False
                            break
                        else:
                            typer.echo("[WARN] 请输入 skip 或 regenerate")
                else:
                    result[key] = False
            return result
        else:
            typer.echo("[WARN] 请输入 continue / restart / select")


def _get_step_description(key: str) -> str:
    """获取步骤描述"""
    descriptions = {
        "direction": "故事方向 (direction.txt)",
        "world": "世界观 (world/world.yaml)",
        "characters": "角色 (characters/*.yaml)",
        "narrator": "叙述者 (narrator.md)",
    }
    return descriptions.get(key, key)


async def step_direction(config: Config, prompt: str, data_dir: Path) -> str:
    """AI 出 3 个故事方向 → 人选择"""
    typer.echo("AI 正在分析你的想法，生成故事方向...")
    directions_text = run_generate_with_retry(config, "quickstart_direction.system", prompt)

    blocks = re.split(r"\n\s*={3,}\s*\n", directions_text)
    blocks = [b.strip() for b in blocks if len(b.strip()) > 50]

    if len(blocks) < 2:
        typer.echo("[WARN] AI 没有正确生成 3 个方案，使用原始输出")
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
            directions_text = run_generate_with_retry(config, "quickstart_direction.system", prompt)
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
                    (data_dir / "direction.txt").write_text(selected, encoding="utf-8")
                    typer.echo(f"  -> 已保存: data/direction.txt")
                    return selected
                else:
                    typer.echo(f"[WARN] 请输入 1-{len(blocks)}")
            except ValueError:
                typer.echo(f"[WARN] 请输入数字 1-{len(blocks)}，或 redo / custom")


async def step_world(config: Config, prompt: str, data_dir: Path) -> str:
    """生成世界观 → 展示 → 人确认/修改"""
    typer.echo("AI 正在构建世界观...")
    world_yaml = run_generate_with_retry(config, "quickstart_world.system", prompt)
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
            world_yaml = run_generate_with_retry(config, "quickstart_world.system", prompt)
            typer.echo("\n--- 重新生成 ---\n")
            typer.echo(world_yaml)
        else:
            revision_prompt = f"原设定:\n{world_yaml}\n\n修改意见: {choice}\n\n请根据修改意见调整世界观设定，输出完整的 YAML。"
            world_yaml = run_generate_with_retry(config, "quickstart_world.system", revision_prompt)
            typer.echo("\n--- 修改后 ---\n")
            typer.echo(world_yaml)

    # 校验 YAML
    import yaml as _yaml
    from moliu.data.schemas import WorldSetting as _WS

    world_path = data_dir / "world" / "world.yaml"
    world_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            data = _yaml.safe_load(world_yaml)
            if not isinstance(data, dict):
                raise ValueError("YAML 不是 dict")
            _WS(**data)
            break
        except Exception as e:
            typer.echo(f"[WARN] 世界观 YAML 校验失败: {e}")
            choice = typer.prompt(
                "[redo] 重新生成 / [edit] 输入修改意见",
                default="redo",
            ).strip().lower()
            if choice == "redo":
                world_yaml = run_generate_with_retry(config, "quickstart_world.system", prompt)
                typer.echo("\n--- 重新生成 ---\n")
                typer.echo(world_yaml)
            else:
                revision_prompt = f"原设定（YAML 格式错误）:\n{world_yaml}\n\n修改意见: {choice}\n\n请输出合法的 YAML。"
                world_yaml = run_generate_with_retry(config, "quickstart_world.system", revision_prompt)
                typer.echo("\n--- 修正后 ---\n")
                typer.echo(world_yaml)

    world_path.write_text(world_yaml, encoding="utf-8")
    typer.echo(f"  -> 已保存: data/world/world.yaml")
    return world_yaml


async def step_characters(
    config: Config,
    prompt: str,
    world: str,
    data_dir: Path,
    rollback: QuickstartRollback | None = None,
) -> list[str]:
    """生成角色 → 展示 → 人确认/逐个修改"""
    typer.echo("AI 正在设计角色...")
    user_prompt = f"故事方向: {prompt}\n\n世界观:\n{world}\n\n请生成 3 个初始角色的人设卡。"
    chars_text = run_generate_with_retry(config, "quickstart_character.system", user_prompt)
    blocks = split_character_blocks(chars_text)

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
            chars_text = run_generate_with_retry(config, "quickstart_character.system", user_prompt)
            blocks = split_character_blocks(chars_text)
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
                    new_block = run_generate_with_retry(config, "quickstart_character.system", rev_prompt)
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
        name = try_validate_character(block)
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


async def step_narrator(config: Config, prompt: str, world: str, chars: list[str], data_dir: Path) -> str:
    """生成叙述者风格 → 展示 → 人确认/修改"""
    typer.echo("AI 正在设计叙述者风格...")
    user_prompt = f"故事: {prompt}\n\n角色: {', '.join(chars)}\n\n请为这部小说设计叙述者风格。"
    narrator_md = run_generate_with_retry(config, "quickstart_narrator.system", user_prompt)
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
            narrator_md = run_generate_with_retry(config, "quickstart_narrator.system", user_prompt)
            typer.echo("\n--- 重新生成 ---\n")
            typer.echo(narrator_md)
        else:
            rev_prompt = f"原风格:\n{narrator_md}\n\n修改意见: {choice}\n\n请根据修改意见调整叙述者风格，输出完整 Markdown。"
            narrator_md = run_generate_with_retry(config, "quickstart_narrator.system", rev_prompt)
            typer.echo("\n--- 修改后 ---\n")
            typer.echo(narrator_md)

    narrator_path = data_dir / "narrator.md"
    narrator_path.write_text(narrator_md, encoding="utf-8")
    typer.echo(f"  -> 已保存: data/narrator.md")
    return narrator_md