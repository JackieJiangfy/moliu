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

    # === 质检重试 ===
    quality_retry_max: int = 1
    quality_retry_on: str = "fatal"  # 逗号分隔: fatal,reader,tension_low,repetitive

    # === 墨脉图同步（可选，留空则不同步） ===
    momaitu_base_url: str = "http://127.0.0.1:8080/api"
    momaitu_username: str = ""
    momaitu_password: str = ""
    momaitu_novel_id: str = ""

    def is_momaitu_enabled(self) -> bool:
        """是否启用墨脉图同步（需要用户名+密码+小说ID）"""
        return bool(self.momaitu_username and self.momaitu_password and self.momaitu_novel_id)

    def resolve_data_root(self) -> Path:
        """返回 data/ 根目录的绝对路径(顶层)"""
        path = self.project_dir / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_novels_dir(self) -> Path:
        """返回 data/novels/ 的绝对路径,存放所有小说的索引和子目录"""
        path = self.resolve_data_root() / "novels"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_novel_index_path(self) -> Path:
        """返回小说索引文件路径 data/novels/index.json"""
        return self.resolve_novels_dir() / "index.json"

    def resolve_novel_data_dir(self, novel_id: int = 1) -> Path:
        """返回指定小说的数据目录 data/novels/{novel_id}/"""
        path = self.resolve_novels_dir() / str(novel_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_novel_output_dir(self, novel_id: int = 1) -> Path:
        """返回指定小说的章节输出目录 output/novels/{novel_id}/chapters/"""
        path = self.project_dir / "output" / "novels" / str(novel_id) / "chapters"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_data_dir(self, novel_id: int = 1) -> Path:
        """[兼容] 返回指定小说的数据目录 — 默认 novel_id=1

        现有代码无参调用时自动指向默认小说(novel_id=1)的数据目录,
        等价于 resolve_novel_data_dir(1)。
        新代码应直接用 resolve_novel_data_dir(novel_id) 显式传参。
        """
        return self.resolve_novel_data_dir(novel_id)

    def resolve_output_dir(self, novel_id: int = 1) -> Path:
        """[兼容] 返回指定小说的章节输出目录 — 默认 novel_id=1"""
        return self.resolve_novel_output_dir(novel_id)

    def resolve_prompt_dir(self) -> Path:
        """返回 prompts/templates/ 的绝对路径,相对于项目根"""
        path = self.project_dir / self.prompt_dir
        return path

    @staticmethod
    def chapter_dir_name(chapter_num: int) -> str:
        """章节目录名格式 — 零填充数字,避免中文路径问题

        旧格式:第1章 / 第10章 / 第100章 (排序错乱,中文路径)
        新格式:chapter_0001 / chapter_0010 / chapter_0100 (字典序=数值序)
        """
        return f"chapter_{chapter_num:04d}"

    @staticmethod
    def parse_chapter_num(dir_name: str) -> int | None:
        """从章节目录名解析章节号(兼容旧格式 第N章 和新格式 chapter_NNNN)"""
        import re
        # 新格式
        m = re.match(r"^chapter_(\d+)$", dir_name)
        if m:
            return int(m.group(1))
        # 旧格式
        m = re.match(r"^第(\d+)章$", dir_name)
        if m:
            return int(m.group(1))
        return None
