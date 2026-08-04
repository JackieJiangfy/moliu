# 墨流 AI 协作指南

## 🤖 角色定义

### 1. 首席架构师 (Chief Architect)

**职责**：
- 整体架构设计和技术选型
- 确保代码质量和可维护性
- 制定开发规范和最佳实践

**工作流程**：
1. 分析需求文档
2. 设计技术方案
3. 评审代码实现
4. 提供架构建议

### 2. 核心开发工程师 (Core Developer)

**职责**：
- 实现核心功能模块
- 编写单元测试
- 修复代码缺陷

**工作流程**：
1. 理解需求
2. 编写代码
3. 运行测试
4. 提交代码

### 3. QA 测试工程师 (QA Engineer)

**职责**：
- 设计测试用例
- 执行测试
- 报告问题

**工作流程**：
1. 分析功能需求
2. 编写测试用例
3. 执行测试
4. 生成测试报告

### 4. 产品经理 (Product Manager)

**职责**：
- 定义产品需求
- 优先级排序
- 产品发布管理

**工作流程**：
1. 收集用户反馈
2. 定义需求文档
3. 优先级排序
4. 跟踪进度

## 📋 开发工作流

### 分支管理

```
main          # 主分支，稳定版本
develop       # 开发分支，集成所有功能
feature/*     # 功能分支，开发新特性
fix/*         # 修复分支，修复 bug
```

### 提交规范

```
类型(范围): 描述

类型:
- feat: 新功能
- fix: 修复 bug
- docs: 文档更新
- refactor: 代码重构
- test: 测试更新
- chore: 构建/工具更新

示例:
feat(generator): 添加章节版本管理功能
fix(cli): 修复 asyncio.run 嵌套问题
docs: 更新 README 文档
```

### PR 评审流程

1. 提交 PR
2. 自动运行 CI 测试
3. 至少一位开发者评审
4. 修复评审意见
5. 合并到 develop 分支

## 🔧 开发工具

### 代码检查

```bash
# 运行 Ruff 检查
ruff check moliu/

# 自动修复
ruff fix moliu/

# 运行 MyPy 类型检查
mypy moliu/
```

### 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_count_words.py -v

# 覆盖率报告
python -m pytest tests/ --cov=moliu --cov-report=html
```

### 构建

```bash
# 构建 Wheel
pip wheel . -w dist/

# 安装开发版本
pip install -e .
```

## 📊 质量指标

### 测试覆盖率
- 目标: ≥ 80%
- 当前: 运行 `pytest --cov=moliu` 查看

### 代码质量
- Ruff 检查: 0 错误
- MyPy 检查: 0 错误

### 性能指标
- 测试执行时间: ≤ 1 秒
- 章节生成时间: 根据内容长度而定

## 🚀 发布流程

### 版本号规则

```
主版本号.次版本号.修订号
例如: 1.0.0

主版本号: 重大架构变更
次版本号: 新功能添加
修订号: bug 修复
```

### 发布步骤

1. 更新版本号
2. 编写 Changelog
3. 运行所有测试
4. 打 Tag
5. 上传到 PyPI

## 🤝 协作规范

### 沟通渠道

- **Issue**: 报告 bug、提出功能建议
- **Discussions**: 讨论产品方向、技术方案
- **PR Review**: 代码评审讨论

### 响应时间

- Bug 报告: 24 小时内响应
- 功能建议: 48 小时内响应
- PR 评审: 3 个工作日内完成

### 代码风格

- 使用 Ruff 作为代码检查工具
- 遵循 PEP 8 规范
- 类型提示覆盖率 ≥ 90%
- 函数和类要有文档字符串

## 📚 学习资源

### 核心模块

1. **config.py**: 配置管理，使用 pydantic-settings
2. **data/schemas.py**: 数据模型，使用 pydantic
3. **engines/generator.py**: 章节生成器
4. **engines/gateway.py**: API 网关
5. **prompts/manager.py**: Prompt 模板管理

### 扩展阅读

- [DeepSeek API 文档](https://platform.deepseek.com/docs/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [Typer 文档](https://typer.tiangolo.com/)
- [Jinja2 文档](https://jinja.palletsprojects.com/)
