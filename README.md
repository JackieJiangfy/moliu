# 墨流 (Moliu)

AI 小说创作工作流引擎 - 帮助作家高效创作长篇小说

## 🌟 特性

- **智能故事生成**：基于 DeepSeek API 的高质量小说内容生成
- **世界观管理**：结构化的世界观设定存储和加载
- **角色管理**：完整的角色人设卡系统，支持状态跟踪和备份
- **叙述者风格**：可定制的叙述者人设卡，支持禁用套话过滤
- **版本控制**：章节多版本管理，支持历史回溯
- **前文回灌**：自动从历史章节提取摘要注入 Prompt
- **快速开始**：交互式创建故事方向、世界观、角色和叙述者

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/JackieJiangfy/moliu.git
cd moliu

# 安装依赖
pip install -e ".[dev]"
```

### 配置

设置 DeepSeek API Key：

```bash
# Linux/Mac
export MO_DEEPSEEK_API_KEY="your-api-key"

# Windows PowerShell
$env:MO_DEEPSEEK_API_KEY="your-api-key"
```

或创建 `.env` 文件：

```
MO_DEEPSEEK_API_KEY=your-api-key
```

### 命令

```bash
# 查看项目状态
mo status

# 初始化项目
mo init

# 快速开始（交互式创建）
mo quickstart -p "都市系统爽文"

# 生成章节
mo write 1 "主角获得系统，完成第一个任务"

# 指定出场角色
mo write 2 "主角遇到第一个反派" --characters "主角,反派" --emotion "紧张"
```

## 📁 项目结构

```
moliu/
├── moliu/                    # 核心代码
│   ├── cli/                  # 命令行接口
│   ├── config.py            # 配置管理
│   ├── data/                 # 数据模型
│   ├── engines/              # 引擎（生成器、网关）
│   └── prompts/              # Prompt 模板管理
├── data/                     # 项目数据（运行时生成）
│   ├── world/                # 世界观设定
│   ├── characters/           # 角色人设卡
│   └── narrator.md           # 叙述者风格
├── output/                   # 输出目录（运行时生成）
│   └── 第N章/                # 章节内容
├── tests/                    # 单元测试
└── pyproject.toml           # 项目配置
```

## 🧪 测试

```bash
# 运行所有测试
python -m pytest tests/

# 排除集成测试
python -m pytest tests/ --ignore=tests/test_integration.py

# 覆盖率报告
python -m pytest tests/ --cov=moliu
```

## 📖 文档

### 角色人设卡格式 (YAML)

```yaml
name: "主角名"
one_line_pitch: "一句话定位"
speech_profile:
  style: "简短、理性"
  sentence_length: "短句为主"
  tone: "陈述句多"
  common_words: ["行", "嗯"]
  banned_words: ["真的吗"]
speech_samples:
  - "\"行。\"（被要求做某事时）"
core:
  core_desire: "核心欲望"
  surface_desire: "表层欲望"
  deep_fear: "深层恐惧"
  value_bottom_line: ["底线1"]
state:
  location: "当前位置"
  current_goal: "当前目标"
  current_emotion: "当前情绪"
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
