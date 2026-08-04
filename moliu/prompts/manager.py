"""Prompt 模板管理器 — Jinja2 加载与渲染"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from moliu.config import Config


class PromptManager:
    """加载和渲染 Prompt 模板"""

    def __init__(self, config: Config):
        template_dir = config.resolve_prompt_dir()
        if not template_dir.exists():
            raise FileNotFoundError(f"模板目录不存在: {template_dir}")
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, **variables) -> str:
        """渲染指定模板"""
        template = self._env.get_template(template_name)
        return template.render(**variables)
