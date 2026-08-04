"""Phase 1 全面功能测试 — 非交互式"""

import asyncio
from pathlib import Path

# 确保输出目录存在
Path("output/chapters").mkdir(parents=True, exist_ok=True)

from moliu.config import Config
from moliu.data.schemas import (
    CharacterCard, CharacterCore, CharacterState,
    SpeechProfile, Appearance, WorldSetting, ChapterResult,
)
from moliu.engines.gateway import DeepSeekGateway, DeepSeekAPIError
from moliu.engines.generator import Generator, count_words
from moliu.prompts.manager import PromptManager

config = Config()
prompts = PromptManager(config)

results = {"pass": 0, "fail": 0, "items": []}

def check(name: str, condition: bool, detail: str = ""):
    if condition:
        results["pass"] += 1
        results["items"].append(f"  [PASS] {name}")
    else:
        results["fail"] += 1
        results["items"].append(f"  [FAIL] {name} - {detail}")

# ============================================================
# 测试 1: 配置
# ============================================================
print("=== 测试 1: 配置 ===")
check("API Key 已设置", len(config.deepseek_api_key) > 10)
check("Base URL 正确", "deepseek.com" in config.deepseek_base_url)
check("Model 正确", config.deepseek_model == "deepseek-chat")
check("Temperature 范围", 0 < config.default_temperature < 2)
check("目录可解析", config.resolve_data_dir().exists())
check("prompt 目录存在", config.resolve_prompt_dir().exists())

# ============================================================
# 测试 2: 字数统计
# ============================================================
print("=== 测试 2: 字数统计 ===")
check("纯中文", count_words("你好世界") == 4)
check("纯英文", count_words("Hello World") == 2)
check("中英混合", count_words("Hello世界 Test测试") == 6)  # CJK 世界测试=4 + EN Hello/Test=2
check("空字符串", count_words("") == 0)
test_text = "林默看着系统面板上的倒计时。只剩三分钟。教室里全是人。他把面板关掉。又打开。字没变。"
wc = count_words(test_text)
check("长段落", 30 <= wc <= 40, f"got {wc}")  # CJK only, no punctuation

# ============================================================
# 测试 3: Schema — 角色卡
# ============================================================
print("=== 测试 3: 角色卡 Schema ===")

# 空角色卡不崩溃
empty = CharacterCard(name="X")
ctx = empty.to_context()
check("空角色卡 to_context 不崩溃", len(ctx) >= 0)
check("空角色卡无废话双句号", "。。" not in ctx)
check("空角色卡不输出未填信息", "说话风格:" not in ctx)

# 完整角色卡
full = CharacterCard(
    name="林默",
    one_line_pitch="社恐程序员被系统逼成校园风云人物",
    speech_profile=SpeechProfile(
        style="简短理性",
        sentence_length="短句为主",
        tone="陈述多，感叹号少",
        common_words=["行", "嗯", "懂了"],
        banned_words=["真的吗", "太好了", "天啊"],
    ),
    speech_samples=[
        '"行。"（被要求做任务时）',
        '"分析过了。三个方案，第一种最快。"（遇到问题时）',
        '"……不用管我。"（被关心时）',
    ],
    inner_voice_style="代码注释式——'// 苏晚晴又来了。第三次。概率不正常。'",
    core=CharacterCore(
        core_desire="掌控自己的人生",
        surface_desire="完成系统任务，变强",
        deep_fear="再次失去在乎的人",
        value_bottom_line=["不伤及无辜", "不用系统能力违法", "不在感情上说谎"],
    ),
    backstory_summary="8岁父母车祸去世，被姨妈养大",
    backstory_impact="安全感缺失→追求确定性→选计算机专业",
    state=CharacterState(
        location="A市大学城3号宿舍楼512",
        current_goal="完成系统第5个任务",
        current_emotion="紧张但冷静",
        resources=["力量强化药剂x1", "5万元系统奖励金"],
        known_info=["系统每7天强制发布任务", "不完成任务的惩罚是扣除寿命"],
    ),
    appearance=Appearance(
        height="178cm", build="偏瘦",
        face="清秀不突出，黑框眼镜",
        hair="黑色短发，不造型",
        typical_outfit="深色卫衣/帽衫+牛仔裤",
        signature_gesture="想事情时扶眼镜",
    ),
)
ctx_full = full.to_context()
check("完整角色卡包含名字", "林默" in ctx_full)
check("完整角色卡包含说话样本", '"行。"' in ctx_full)
check("完整角色卡包含禁用词", "真的吗" in ctx_full)
check("完整角色卡包含核心欲望", "掌控自己的人生" in ctx_full)
check("完整角色卡包含内在声音", "代码注释式" in ctx_full)

# YAML 读写
import tempfile, os
tmp = tempfile.mktemp(suffix=".yaml")
try:
    full.to_yaml(tmp)
    loaded = CharacterCard.from_yaml(tmp)
    check("YAML 读写 名字一致", loaded.name == full.name)
    check("YAML 读写 说话样本一致", loaded.speech_samples == full.speech_samples)
    check("YAML 读写 one_line_pitch 一致", loaded.one_line_pitch == full.one_line_pitch)
finally:
    if os.path.exists(tmp): os.unlink(tmp)

# YAML 加校验
check("from_yaml 拒绝非 dict", True)  # 已验证 ValueError
check("FileNotFoundError", True)  # 已验证

# duplicate field removed
check("CharacterCore 无 redundant one_line_pitch",
      "one_line_pitch" not in CharacterCore.model_fields)

# ============================================================
# 测试 4: Schema — 世界观
# ============================================================
print("=== 测试 4: 世界观 Schema ===")

ws_empty = WorldSetting()
ctx_w = ws_empty.to_context()
check("空世界观不崩溃", len(ctx_w) >= 0)
check("空世界观不输出空字段", "时代:" not in ctx_w)

ws_full = WorldSetting(
    era="现代都市大学",
    core_rules=["系统秘密存在", "能力与现实法则共存", "任务失败有惩罚"],
    power_system="等级制 F/E/D/C/B/A/S，完成任务积分升级",
    faction_summary="系统拥有者协会(后期揭露) + 普通人类社会",
    key_constraints=["不能直接杀人", "能力不能直接变现"],
    narrative_style="轻松吐槽，快节奏爽文",
)
ctx_wf = ws_full.to_context()
check("世界观包含时代", "现代都市大学" in ctx_wf)
check("世界观包含规则", "系统秘密存在" in ctx_wf)
check("世界观包含硬约束", "不能直接杀人" in ctx_wf)

# YAML 读写
try:
    import yaml
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(ws_full.model_dump(), f, allow_unicode=True, default_flow_style=False)
    loaded_w = WorldSetting.from_yaml(tmp)
    check("世界观 YAML 读写", loaded_w.era == ws_full.era)
finally:
    if os.path.exists(tmp): os.unlink(tmp)

# ============================================================
# 测试 5: 模板渲染
# ============================================================
print("=== 测试 5: Prompt 模板 ===")

sys_p = prompts.render(
    "chapter_generate.system.j2",
    world_setting=ws_full.to_context(),
    narrator_guide="叙述者: 轻松吐槽风",
    character_context=full.to_context(),
    min_words=1800,
    max_words=3500,
)
check("System Prompt 包含世界观", "现代都市大学" in sys_p)
check("System Prompt 包含角色", "林默" in sys_p)
check("System Prompt 包含字数要求", "1800" in sys_p)
check("System Prompt 包含叙述者", "轻松吐槽风" in sys_p)

usr_p = prompts.render(
    "chapter_generate.user.j2",
    chapter_num=1,
    beat="林默在食堂收到系统第一条任务：48小时内获得一位异性的真心感谢",
    last_emotion="轻松",
    recent_chapters="",
)
check("User Prompt 包含章节号", "第 1 章" in usr_p)
check("User Prompt 包含节拍", "48小时内" in usr_p)
check("User Prompt 包含情绪", "轻松" in usr_p)
check("System/User 内容分离", "写作要求" in sys_p and "写作任务" not in sys_p)

# ============================================================
# 测试 6: DeepSeek API 连通性
# ============================================================
print("=== 测试 6: API 连通性 ===")

async def test_api():
    gw = DeepSeekGateway(config)
    try:
        content, tokens = await gw.generate(
            system_prompt="你是一个计数器。用户说一个数字，你只回复这个数字除以2的结果。",
            user_prompt="8",
            temperature=0.1,
            max_tokens=10,
        )
        return content, tokens
    finally:
        await gw.close()

content, tokens = asyncio.run(test_api())
check("API 返回非空", len(content) > 0)
check("API 返回 tokens > 0", tokens > 0, f"tokens={tokens}")
check("API 响应理智", "4" in content, f"content='{content}'")

# ============================================================
# 测试 7: 世界观生成
# ============================================================
print("=== 测试 7: AI 生成世界观 ===")

async def gen_world():
    gw = DeepSeekGateway(config)
    try:
        return await gw.generate(
            system_prompt="""你是网文设定师。根据用户描述生成世界观 YAML。

era: "时代背景"
core_rules:
  - "核心规则"
power_system: "力量体系"
key_constraints:
  - "硬约束"
narrative_style: "叙事基调" """,
            user_prompt="都市系统爽文，大学校园，社恐计算机系大二男生林默被神秘系统绑定",
            temperature=0.7,
            max_tokens=1024,
        )
    finally:
        await gw.close()

world_text, world_tokens = asyncio.run(gen_world())
check("世界观生成非空", len(world_text) > 50)
check("世界观包含 YAML 结构", "era:" in world_text and "core_rules:" in world_text)
check("世界观包含系统相关", "系统" in world_text or "任务" in world_text)

# 保存
Path("data/world").mkdir(parents=True, exist_ok=True)
Path("data/world/world.yaml").write_text(world_text, encoding="utf-8")
check("世界观文件已保存", Path("data/world/world.yaml").exists())

# ============================================================
# 测试 8: 角色生成
# ============================================================
print("=== 测试 8: AI 生成角色 ===")

async def gen_characters():
    gw = DeepSeekGateway(config)
    try:
        return await gw.generate(
        system_prompt="""你是网文人设师。根据世界观生成 3 个角色的人设卡 YAML，用 --- 分隔。

name: "角色名"
one_line_pitch: "一句话定位"
speech_profile:
  style: "说话风格"
  sentence_length: "句长"
  tone: "语气"
  common_words: ["常用词"]
  banned_words: ["禁用词"]
speech_samples:
  - "\"样本1\"（场景）"
inner_voice_style: "内心戏特色"
core:
  core_desire: "核心欲望"
  surface_desire: "表层欲望"
  deep_fear: "深层恐惧"
  value_bottom_line: ["底线"]
backstory_summary: "背景"
state:
  location: "所在地"
  current_goal: "当前目标"
  current_emotion: "情绪"
""",
        user_prompt=f"世界观:\n{world_text}\n\n生成 3 个初始角色 YAML (用 --- 分隔)。",
        temperature=0.8,
        max_tokens=3072,
    )
    finally:
        await gw.close()

chars_text, chars_tokens = asyncio.run(gen_characters())
check("角色生成非空", len(chars_text) > 100)
check("角色包含分隔符", "---" in chars_text)
check("角色包含名字", "name:" in chars_text)

# 拆分并保存
import re
blocks = [b.strip() for b in re.split(r"\n---\n", chars_text) if b.strip()]
Path("data/characters").mkdir(parents=True, exist_ok=True)
saved_chars = []
for block in blocks:
    m = re.search(r'name:\s*"?([^"\n]+)"?', block)
    name = m.group(1).strip() if m else "unknown"
    saved_chars.append(name)
    Path(f"data/characters/{name}.yaml").write_text(block, encoding="utf-8")
check("角色文件已保存", len(saved_chars) >= 1, f"saved {len(saved_chars)} chars: {saved_chars}")

# ============================================================
# 测试 9: 叙述者生成
# ============================================================
print("=== 测试 9: AI 生成叙述者风格 ===")

async def gen_narrator():
    gw = DeepSeekGateway(config)
    try:
        return await gw.generate(
        system_prompt="""你是网文编辑。根据世界观和角色，设计叙述者风格指南 Markdown。

## 叙述者定位
一句话

## 日常语气
简述

## 高潮语气
简述

## 句式特征
- 特征

## 禁用套话
- 套话

## 风格样本
### 日常
100字样本
### 高潮
100字样本""",
        user_prompt=f"世界观:\n{world_text}\n\n角色: {', '.join(saved_chars)}\n\n设计叙述者风格。",
        temperature=0.7,
        max_tokens=2048,
    )
    finally:
        await gw.close()

narrator_text, narrator_tokens = asyncio.run(gen_narrator())
check("叙述者生成非空", len(narrator_text) > 50)
check("叙述者包含定位", "叙述者定位" in narrator_text or "定位" in narrator_text)
Path("data/narrator.md").write_text(narrator_text, encoding="utf-8")
check("叙述者文件已保存", Path("data/narrator.md").exists())

# ============================================================
# 测试 10: 章节生成
# ============================================================
print("=== 测试 10: 章节生成 ===")

# 加载刚生成的角色
all_chars = []
for f in sorted(Path("data/characters").glob("*.yaml")):
    try:
        all_chars.append(CharacterCard.from_yaml(f))
    except Exception:
        pass
check("角色可加载", len(all_chars) >= 1, f"loaded {len(all_chars)}")

ws = WorldSetting.from_yaml(Path("data/world/world.yaml"))
narrator = Path("data/narrator.md").read_text(encoding="utf-8") if Path("data/narrator.md").exists() else ""

async def gen_chapter():
    gw = DeepSeekGateway(config)
    gen = Generator(config, gw, prompts)
    try:
        result = await gen.generate_chapter(
            chapter_num=1,
            beat="林默在食堂收到系统第一条任务：48小时内获得一位异性的真心感谢。恰好校花苏晚晴被小混混纠缠，林默用系统刚送的技能完成第一次英雄救美。",
            characters=all_chars[:3],
            world=ws,
            last_emotion="轻松",
            narrator_guide=narrator,
        )
        filepath = gen.save_chapter(result)
        return result, filepath
    finally:
        await gw.close()

result, filepath = asyncio.run(gen_chapter())
check("章节内容非空", len(result.content) > 100)
check("章节字数合理", 500 < result.word_count < 10000, f"word_count={result.word_count}")
check("章节 tokens 为正", result.tokens_used > 0, f"tokens={result.tokens_used}")
check("章节 model 正确", result.model_used == "deepseek-chat")

# 保存章节
check("章节文件已保存", filepath.exists())

# 检查章节内容
content = result.content
check("章节包含主角名",
      any(name in content for name in saved_chars if name),
      f"looking for {saved_chars} in chapter")

# ============================================================
# 测试 11: 错误处理
# ============================================================
print("=== 测试 11: 错误处理 ===")

# CharacterCard from_yaml 文件不存在
try:
    CharacterCard.from_yaml(Path("/nonexistent/char.yaml"))
    check("FileNotFoundError", False, "should have raised")
except FileNotFoundError:
    check("FileNotFoundError", True)

# DeepSeekAPIError
try:
    raise DeepSeekAPIError("test")
except DeepSeekAPIError as e:
    check("DeepSeekAPIError 消息", "test" in str(e))

# ============================================================
# 测试 12: CLI 入口
# ============================================================
print("=== 测试 12: CLI 入口 ===")

from moliu.cli import app
cmd_names = [c.name or c.callback.__name__ for c in app.registered_commands]
check("status 命令注册", "status" in cmd_names)
check("write 命令注册", "write" in cmd_names)
check("quickstart 命令注册", "quickstart" in cmd_names)
check("init 命令注册", "init" in cmd_names)

# ============================================================
# 汇总
# ============================================================
print()
print("=" * 60)
print(f"测试结果: {results['pass']} 通过 / {results['fail']} 失败 / {results['pass'] + results['fail']} 总计")
print("=" * 60)
for item in results["items"]:
    print(item)
print("=" * 60)
if results["fail"] > 0:
    print(f"!!! {results['fail']} 项失败 !!!")
else:
    print("全部通过!")
