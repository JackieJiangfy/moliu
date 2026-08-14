# 墨流 (Moliu)

AI 小说创作工作流引擎 — 帮助作家高效创作长篇小说

## 🌟 特性

- **Web 创作工作台**:单页 HTML 界面,五个核心 Tab(对话创作 / 卷宗规划 / 章节列表 / 世界设定 / 关系图谱)
- **OpenAI 兼容 API**:后端暴露 `/v1/models`、`/v1/chat/completions`,可被任意兼容客户端调用
- **智能故事生成**:基于 DeepSeek API 的高质量小说内容生成,支持分段生成(开篇/中段/结尾)
- **结构化上下文装配**:大纲 + 人物表 + 伏笔 + 关系图谱 + 前文原文,精确查询而非语义检索
- **生成前 Gatekeeper**:7 项强制校验(卷归属 / 大纲 / 节拍 / 出场角色 / 上一章元数据 / 伏笔状态 / 章节号)
- **质量保障闭环**:一致性检查 + 读者评估 + 张力评分 + 节奏追踪 + 去 AI 味
- **世界观与角色管理**:结构化存储,支持状态跟踪和版本备份
- **章节版本管理**:多版本保存,支持历史回溯
- **CLI 命令行**:批量生成、元数据回填、状态查询

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/JackieJiangfy/moliu.git
cd moliu

# 安装依赖(含开发与测试工具)
pip install -e ".[dev]"
```

### 配置

复制 `.env.example` 为 `.env` 并填入 DeepSeek API Key:

```bash
cp .env.example .env
```

```env
MO_DEEPSEEK_API_KEY=sk-your-key-here
```

或在终端设置环境变量:

```bash
# Linux/Mac
export MO_DEEPSEEK_API_KEY="your-api-key"

# Windows PowerShell
$env:MO_DEEPSEEK_API_KEY="your-api-key"
```

### 启动 Web 工作台

```bash
# 启动 FastAPI 后端(开发模式,热重载)
python -m uvicorn moliu.api:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 http://localhost:8000 即可进入创作工作台。

### CLI 用法

```bash
# 查看项目状态
mo status

# 初始化项目
mo init

# 快速开始(交互式创建故事方向、世界观、角色和叙述者)
mo quickstart -p "都市系统爽文"

# 生成章节
mo write 1 "主角获得系统,完成第一个任务"

# 指定出场角色
mo write 2 "主角遇到第一个反派" --characters "主角,反派" --emotion "紧张"
```

## 📁 项目结构

```
moliu/
├── moliu/                       # 核心代码
│   ├── api/                     # FastAPI 后端
│   │   ├── routes/              # REST 路由(volumes/chapters/characters/world/foreshadows/relationships)
│   │   └── __init__.py          # create_app()
│   ├── cli/                     # Typer 命令行接口
│   ├── config.py                # Pydantic Settings 配置管理
│   ├── context/assembler.py    # 结构化上下文组装器
│   ├── data/schemas.py          # 数据模型(角色卡/世界观/章节元数据)
│   ├── engines/                 # 引擎层
│   │   ├── generator.py         # 章节生成器(分段)
│   │   ├── gateway.py           # DeepSeek API 网关
│   │   ├── gatekeeper.py        # 生成前强制校验
│   │   ├── checker.py           # 一致性检查
│   │   ├── reader_eval.py       # 读者评估
│   │   ├── backfill.py          # 元数据回填
│   │   └── usage.py             # Token 用量统计
│   ├── memory/                  # 记忆系统(ChromaDB + JSON 回退)
│   ├── rules/                   # 规则引擎(伏笔追踪、节奏追踪)
│   ├── deai/                    # 去 AI 味(detector + rewriter)
│   ├── orchestrator/pipeline.py # 章节生成编排管线
│   ├── prompts/                 # Jinja2 Prompt 模板
│   ├── sync/                    # 墨脉图同步(可选)
│   └── static/index.html        # 单页创作工作台
├── data/                        # 项目数据(运行时生成)
│   ├── world/                   # 世界观设定
│   ├── characters/              # 角色人设卡
│   ├── outlines/                # 章节大纲
│   ├── volumes/index.json       # 卷宗索引
│   └── ...
├── output/chapters/             # 章节输出(第N章/正文.md + meta.json)
├── tests/                       # 单元测试
└── pyproject.toml              # 项目配置
```

## 🔌 API 端点

### 创作工作台 REST API(`/api/v1`)

| 路由 | 说明 |
|---|---|
| `GET /api/v1/status` | 项目概览 |
| `GET/POST/PUT/DELETE /api/v1/volumes` | 卷宗 CRUD |
| `GET/POST/PUT/DELETE /api/v1/chapters` | 章节列表与生成 |
| `GET /api/v1/chapters/{n}/context` | 章节生成前上下文预览 |
| `GET /generate/check` | Gatekeeper 生成前预检 |
| `GET/POST/PUT/DELETE /api/v1/characters` | 角色 CRUD |
| `GET/POST/PUT/DELETE /api/v1/world` | 世界观 CRUD |
| `GET/POST/PUT/DELETE /api/v1/foreshadows` | 伏笔 CRUD |
| `GET/POST/PUT/DELETE /api/v1/relationships` | 关系 CRUD(25 种预设类型) |
| `GET /api/v1/graph` | 关系图谱数据(节点+边,供 ECharts 渲染) |

### OpenAI 兼容接口(`/v1`)

| 路由 | 说明 |
|---|---|
| `GET /v1/models` | 模型列表(章节生成助手、大纲规划助手、元数据回填助手) |
| `POST /v1/chat/completions` | 对话接口(SSE 流式) |

## 🧪 测试

```bash
# 运行所有测试
python -m pytest tests/

# 排除集成测试(需要真实 API Key)
python -m pytest tests/ --ignore=tests/test_integration.py

# 覆盖率报告
python -m pytest tests/ --cov=moliu
```

## 📖 文档

### 角色人设卡格式(YAML)

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
  - "\"行。\"(被要求做某事时)"
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

欢迎提交 Issue 和 Pull Request!

## 📄 许可证

MIT License
