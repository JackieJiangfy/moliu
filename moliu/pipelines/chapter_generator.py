"""
墨流 · 章节生成助手 — OpenWebUI Pipelines 插件

在 OpenWebUI 中注册为虚拟模型「📝 章节生成助手」。
用户在聊天中输入章节信息，插件自动调用墨流后端 API 生成章节。

安装方式:
  1. 将本文件放入 OpenWebUI 的 pipelines 目录
  2. 在 OpenWebUI 设置中启用此 pipeline
  3. 模型列表中会出现「📝 章节生成助手」

环境变量:
  MOLIU_API_URL: 墨流后端地址（默认 http://host.docker.internal:8000）
"""

from typing import Optional

# 尝试导入 OpenWebUI Pipeline 基类（如果不存在则提供桩）
try:
    from pipelines.base import Pipeline as BasePipeline
except ImportError:
    class BasePipeline:
        """桩 — 允许在 IDE 中正常开发"""
        pass

import httpx


class Pipeline(BasePipeline):
    """章节生成助手 Pipeline"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "📝 章节生成助手"
        self.description = "通过墨流引擎生成小说章节"
        self.moliu_api_url = "http://host.docker.internal:8000"

    async def on_startup(self, **kwargs):
        """启动时加载配置"""
        import os
        self.moliu_api_url = os.getenv("MOLIU_API_URL", self.moliu_api_url)
        # 校验后端可达性
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{self.moliu_api_url}/api/v1/status", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    self.name = f"📝 章节生成助手 ({data.get('novel_title', '未命名')})"
        except Exception:
            pass  # 不可达也不阻塞

    async def pipe(self, body: dict, messages: list[dict], user_message: str, **kwargs) -> str:
        """
        处理用户消息

        支持两种输入格式:
          1. 自然语言: "生成第126章，沈夜发现验钞机56%的真相"
          2. 结构化: "第126章 | 沈夜发现验钞机56%的真相 | 紧张"
        """
        # 解析用户消息
        chapter_num, beat, emotion = self._parse_message(user_message)
        if not chapter_num or not beat:
            return (
                "请按以下格式输入章节信息：\n\n"
                "  格式1: 生成第126章，沈夜发现验钞机56%的真相\n"
                "  格式2: 第126章 | 沈夜发现验钞机56%的真相 | 紧张\n\n"
                "必填：章节号 + 节拍描述\n"
                "可选：情绪标签（默认：轻松）"
            )

        # 预检
        try:
            async with httpx.AsyncClient() as client:
                params = {
                    "chapter_num": chapter_num,
                    "beat": beat,
                    "emotion": emotion,
                }
                r = await client.get(
                    f"{self.moliu_api_url}/api/v1/generate/check",
                    params=params,
                    timeout=10,
                )
                check = r.json()

                if not check.get("passed"):
                    lines = ["## ❌ 预检未通过，请修复以下问题：\n"]
                    for item in check.get("missing_items", []):
                        lines.append(f"- {item}")
                    if check.get("warnings"):
                        lines.append("\n**建议：**")
                        for w in check.get("warnings", []):
                            lines.append(f"- ⚠ {w}")
                    return "\n".join(lines)

                # 预检通过，给出生成命令
                hints = check.get("context_hints", [])
                cmd = f"mo write {chapter_num} \"{beat}\" --emotion {emotion}"
                result = [
                    f"## ✅ 预检通过！\n",
                    f"**章节**: 第 {chapter_num} 章",
                    f"**节拍**: {beat}",
                    f"**情绪**: {emotion}",
                ]
                if hints:
                    result.append("\n**提示：**")
                    for h in hints:
                        result.append(f"- 💡 {h}")
                result.append(f"\n请在终端运行以下命令生成：\n\n```bash\n{cmd}\n```")
                return "\n".join(result)

        except httpx.RequestError as e:
            return f"## ❌ 无法连接到墨流后端\n\n请确认后端已启动：`mo serve`\n\n错误: {e}"

    def _parse_message(self, msg: str) -> tuple[Optional[int], Optional[str], str]:
        """解析用户消息，返回 (chapter_num, beat, emotion)"""
        msg = msg.strip()

        # 格式2: "第126章 | 沈夜发现... | 紧张"
        if "|" in msg:
            parts = [p.strip() for p in msg.split("|")]
            if len(parts) >= 2:
                ch = self._extract_chapter_num(parts[0])
                return ch, parts[1], parts[2] if len(parts) > 2 else "轻松"

        # 格式1: "生成第126章，沈夜发现..."
        chapter_num = self._extract_chapter_num(msg)
        if chapter_num:
            # 去掉章节号部分，剩余作为节拍
            import re
            beat = re.sub(r"生成?\s*第?\s*\d+\s*章?[,，:：\s]*", "", msg, count=1).strip()
            if beat:
                return chapter_num, beat, "轻松"

        return None, None, "轻松"

    @staticmethod
    def _extract_chapter_num(text: str) -> Optional[int]:
        """从文本中提取章节号"""
        import re
        matches = re.findall(r"第?\s*(\d+)\s*章", text)
        if matches:
            return int(matches[-1])
        return None