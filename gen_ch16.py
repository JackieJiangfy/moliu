"""Chapter 16 — 白露的窗台"""
import asyncio
from pathlib import Path
from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.generator import Generator
from moliu.context.assembler import StructuredAssembler
from moliu.prompts.manager import PromptManager

config = Config()
gateway = DeepSeekGateway(config)
prompts = PromptManager(config)
chars = [CharacterCard.from_yaml(f) for f in Path("data/characters").glob("*.yaml") if "sample" not in f.name]
world = WorldSetting.from_yaml(Path("data/world/world.yaml"))
ch15 = Path("output/chapters/第15章/正文.md").read_text(encoding="utf-8")

VOICE = """沈夜嘴欠密度保持。老白和沈夜的对话要有来有回。本章是白露案的推进章——沈夜回到那栋旧楼调查窗台上的压痕，发现关键线索。结尾要有新钩子。"""

async def main():
    beat = ("收到那条消息后沈夜连夜回到白露旧居。梧桐里七号三楼。他重新检查窗台——那道压痕不是坠楼留下的，"
            "是有人从外面爬进来。窗框底部有一片半枚指纹，是老式铁锈上留下的。他拍了照发给孟小鱼让地府档案库比对。"
            "孟小鱼凌晨回消息：指纹匹配——白露学校的体育老师，三年前因猥亵学生被开除，但从未被起诉。"
            "沈夜盯着这个名字看了很久。他想起白露最后那句话：跟我爸说，我那天没偷东西。"
            "第二天他带着线索去找老周。老周看了照片，手开始抖——那天在学校门口等白露的黑衣男人，就是这个人。"
            "沈夜回到银行，在白露的档案备注栏加了一行字：嫌疑人已锁定。下一步——找证据。"
            "验钞机叮了一声。新消息：白七爷的预约到访时间——明天下午。")

    asm = StructuredAssembler(config)
    ctx = asm.assemble(16, beat, chars, world, narrator_guide=VOICE, last_emotion="紧张")

    gen = Generator(config, gateway, prompts)
    result = await gen.generate_chapter(
        chapter_num=16, beat=beat, characters=chars, world=world,
        last_emotion="紧张", recent_chapters=ch15[-1200:],
        narrator_guide=VOICE, temperature=0.95, segmented=False,
        chapter_type="normal",
    )
    path = gen.save_chapter(result)
    print(f"Ch16: {result.word_count} words")

asyncio.run(main())
