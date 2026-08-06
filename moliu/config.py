"""配置管理 — 从环境变量加载，Pydantic 校验"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === DeepSeek API ===
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout: int = 120
    deepseek_max_retries: int = 3

    # === 路径 ===
    project_dir: Path = Path(__file__).parent.parent
    data_dir: Path = Path("data")
    output_dir: Path = Path("output/chapters")
    prompt_dir: Path = Path("moliu/prompts/templates")

    # === 生成参数 ===
    default_temperature: float = 0.8
    default_max_tokens: int = 4096
    chapter_min_words: int = 1800
    chapter_max_words: int = 3500

    # === 墨脉图同步（可选，留空则不同步） ===
    momaitu_base_url: str = "http://127.0.0.1:8080/api"
    momaitu_username: str = ""
    momaitu_password: str = ""
    momaitu_novel_id: str = ""

    def is_momaitu_enabled(self) -> bool:
        """是否启用墨脉图同步（需要用户名+密码+小说ID）"""
        return bool(self.momaitu_username and self.momaitu_password and self.momaitu_novel_id)

    def resolve_data_dir(self) -> Path:
        """返回 data/ 的绝对路径"""
        path = self.project_dir / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_output_dir(self) -> Path:
        """返回 output/ 的绝对路径"""
        path = self.project_dir / self.output_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_prompt_dir(self) -> Path:
        """返回 prompts/templates/ 的绝对路径，相对于项目根"""
        path = self.project_dir / self.prompt_dir
        return path
