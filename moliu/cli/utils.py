"""CLI 通用工具函数"""

from pathlib import Path

import typer
import yaml

from moliu.config import Config
from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting


def load_config() -> Config:
    """加载配置，处理错误"""
    try:
        return Config()
    except Exception as e:
        typer.echo(f"[ERROR] 配置加载失败: {e}")
        typer.echo("请确保设置了 MO_DEEPSEEK_API_KEY 环境变量或 .env 文件")
        raise typer.Exit(code=1)


def load_characters(config: Config) -> list[CharacterCard]:
    """加载所有角色卡"""
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


def load_world(config: Config) -> WorldSetting | None:
    """加载世界观设定"""
    world_path = config.resolve_data_dir() / "world" / "world.yaml"
    if not world_path.exists():
        return None
    return WorldSetting.from_yaml(world_path)


def load_narrator(config: Config) -> NarratorCard | None:
    """加载叙述者卡（优先 Markdown，其次 YAML）"""
    narrator_md_path = config.resolve_data_dir() / "narrator.md"
    if narrator_md_path.exists():
        return NarratorCard.from_markdown(narrator_md_path)

    narrator_yaml_path = config.resolve_data_dir() / "narrator.yaml"
    if narrator_yaml_path.exists():
        return NarratorCard.from_yaml(narrator_yaml_path)

    return None


def try_validate_character(yaml_text: str) -> str | None:
    """验证角色 YAML，成功返回角色名"""
    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return None
        card = CharacterCard(**data)
        return card.name
    except Exception:
        return None


def split_character_blocks(text: str) -> list[str]:
    """按 --- 分隔符拆分角色 YAML 块"""
    import re
    blocks = re.split(r"\n---\n", text)
    return [b.strip() for b in blocks if b.strip()]


class QuickstartRollback:
    """跟踪 quickstart 写入的文件，失败时回滚"""

    def __init__(self):
        self._tracked: dict[Path, str | None] = {}

    def track(self, path: Path) -> None:
        """写入前记录文件状态"""
        if path.exists():
            self._tracked[path] = path.read_text(encoding="utf-8")
        else:
            self._tracked[path] = None

    def undo(self) -> None:
        """回滚所有跟踪的文件"""
        for path, original in self._tracked.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(original, encoding="utf-8")
            except OSError:
                pass
        self._tracked.clear()