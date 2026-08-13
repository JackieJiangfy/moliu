"""Generate Chapters 26-30 with graph injection"""
import asyncio
from pathlib import Path
from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.generator import Generator
from moliu.context.assembler import StructuredAssembler
from moliu.prompts.manager import PromptManager

config = Config()
chars = [CharacterCard.from_yaml(f) for f in Path("data/characters").glob("*.yaml") if "sample" not in f.name]
world = WorldSetting.from_yaml(Path("data/world/world.yaml"))
VOICE = "沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。每章结尾验钞机亮一次留下悬念。"

beats = {
    26: ("验钞机倒计时还剩 68 小时。沈夜决定大规模处理坏账——不是还钱，是债务重组。"
         "老白翻出三百年的旧账本，两人连夜把坏账分类：能盘活的、能打包的、能赖掉的、必须认的。"
         "凌晨两点，老白忽然从一堆旧账里抬起头：你爹当年也这么干过——分类分到最后一笔的时候，他跑了。"
         "沈夜头也没抬：他那笔是什么。老白说：是一笔他不想认的账。沈夜的手停了。是什么。老白没回答。"),
    27: ("孟小鱼带来消息：地府债务减免政策下来了——亡灵银行符合条件。但有个附加条件。"
         "条件：法人必须在三年内让亡灵银行扭亏为盈，否则不仅银行关停，法人的阳间财产也将被冻结。"
         "沈夜看着条款：也就是说我要是搞砸了，房租都交不起。孟小鱼说对。沈夜说那跟现在有什么区别。"
         "孟小鱼没笑。她说签不签随你。但我告诉你——你爹当年也遇到过这个政策，他没签。"
         "沈夜拿起笔：他跟我不一样。他跑了。我不会。"),
    28: ("签完文件的第二天，一个意想不到的客户上门——是地府财政司的退休老司长。"
         "老头七十多岁，拄着拐杖，西装笔挺。他说我不是鬼——我是活人。沈夜站起来。"
         "老头说我认识你爹。他退休之前，沈万通是他手下最头疼的法人——也是唯一一个让他在审计报告上签过'合格'的。"
         "老头从公文包里掏出一份泛黄的审计报告，放在桌上：这是你爹唯一一份合格的报告。你看看日期。"
         "沈夜翻开报告。日期是十九年前——他七岁那年。他爹跑路的前一个月。"),
    29: ("审计报告上只有一行字：法人沈万通已将全部个人资产划入银行储备金，用于偿还客户存款。"
         "沈夜盯着这行字看了很久。他爹跑路之前，把自己所有的钱都填进银行了。他不是空手跑的——他把能给的都给了。"
         "老头说后来我才知道——他跑不是躲债。是他欠了一笔不能用钱还的债。有人要他的命。"
         "沈夜问是谁。老头看了一眼验钞机屏幕上的倒计时——还剩 20 小时。他说你很快就会知道了。"),
    30: ("倒计时归零前最后一小时。沈夜坐在柜台后面，把所有账本整理好。老白站在旁边。"
         "验钞机忽然响了——不是新业务，是一行他从未见过的字：账户余额查询——法人沈万通个人账户。余额：1 功德币。"
         "备注栏有一行他爹的字：小夜，我留了一块钱。不是给你的。是给银行的第一笔存款。这样它就不算空壳公司了。"
         "沈夜盯着那行字看了很久。倒计时跳到零。验钞机屏幕暗了一下，又亮了：新业务接入——申请人未知。"
         "卷终。"),
}

for ch_num, beat in beats.items():
    gw = DeepSeekGateway(config)
    prompts = PromptManager(config)
    asm = StructuredAssembler(config)

    prev_path = Path(f"output/chapters/第{ch_num - 1}章/正文.md")
    recent = prev_path.read_text(encoding="utf-8")[-1500:] if prev_path.exists() else ""
    ctx = asyncio.run(asm.assemble(ch_num, beat, chars, world, narrator_guide=VOICE, last_emotion="紧张"))
    print(f"Ch{ch_num} graph: {len(ctx.graph_insights)}c")

    gen = Generator(config, gw, prompts)
    result = asyncio.run(gen.generate_chapter(
        chapter_num=ch_num, beat=beat, characters=chars, world=world,
        last_emotion="紧张", recent_chapters=recent, narrator_guide=VOICE,
        temperature=0.95, segmented=False,
        chapter_type="climax" if ch_num == 30 else "normal",
    ))
    gen.save_chapter(result)
    print(f"Ch{ch_num}: {result.word_count}w")

print("Done! 26-30 generated.")
