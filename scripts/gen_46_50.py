import asyncio
from pathlib import Path
from moliu.config import Config
from moliu.data.schemas import CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.generator import Generator
from moliu.context.assembler import StructuredAssembler
from moliu.prompts.manager import PromptManager

config = Config()
chars = [CharacterCard.from_yaml(f) for f in Path('data/characters').glob('*.yaml') if 'sample' not in f.name]
world = WorldSetting.from_yaml(Path('data/world/world.yaml'))
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。悬念推进。'

beats = {
    46: '验钞机上的数字跳到了52%。沈夜花了三天处理完一批旧账——七个客户的债务重组方案全部签完。老白在旁边用算盘核对完最后一笔说你这效率比你爹高了三倍。沈夜说那是因为我不用躲债。赵铁面派人送来一份文件——是沈万通当年写的坏账处理手册，里面详细记录了每一笔坏账的来源和解决方案。沈夜翻开第一页。他爹的字迹：小夜，这些账我都算过了。我只是来不及处理。',
    47: '一个穿校服的高中生鬼魂推门进来。他死于校园霸凌，执念是考试没考完——他死的那天是高考前一天。他想考完那场试。沈夜说地府没有高考。他说我知道但我就是想知道那道压轴题答案。沈夜打开电脑找到了去年的高考真题。他把数学卷子打印出来放在柜台上。那鬼魂飘在柜台后面，用透明的手握着笔，写了一下午。交卷的时候沈夜给他批了分——127。能上本科。那鬼魂说谢谢。然后投胎去了。验钞机叮了一声：52%→54%。',
    48: '孟小鱼带了一个文件袋来银行——不是公务，是一个私人请求。她妈明天七十大寿，她需要一笔功德币给她妈买一个健康符。她攒了三年不够。沈夜说你一个地府公务员找我私人贷款。孟小鱼说不然我找谁——我认识的人里没有放贷的活人。沈夜看了她很久。然后他打开Excel说利息按银行内部员工价算。孟小鱼签完借据抬头看他：你比你爹会做人。沈夜说我只是比你爹怕被你催债。',
    49: '赵铁面深夜来访。他坐在沈夜对面说渡劫基金的事已经传出去了——地府高层有人知道那笔钱的存在。有人想提前解冻——不是帮你，是想抢。沈夜问谁。赵铁面说财政司新上任的副司长姓蒋，是你爹当年的死对头之一。他比你爹年轻，比你爹狠，而且他手里有你爹的一份亲笔信——当年沈万通写的承诺书。承诺书的内容是如果亡灵银行无法正常经营，渡劫基金的全部资产将移交给财政部。赵铁面说那份承诺书在法律上是有效的。除非你能证明银行在正常经营。',
    50: '沈夜把银行过去三十天的经营数据全部打印出来。流水、债务重组方案、客户满意度调查、地府民政局盖章的审计通过通知书。他把这摞纸装订成册，封面手写了一行字：亡間银行经营报告——法人沈夜。他让老白把报告送到财政司。老白说你不去。沈夜说我不去——我留着看店。老白抱着报告走出巷口的时候回头看了一眼沈夜。沈夜靠着门框，嘴里叼着一根没点着的烟，手指弹着验钞机外壳。屏幕上的数字安静地亮着：56%。',
}

for ch_num, beat in beats.items():
    gw = DeepSeekGateway(config)
    prompts = PromptManager(config)
    asm = StructuredAssembler(config)
    prev_path = Path(f'output/chapters/第{ch_num - 1}章/正文.md')
    recent = prev_path.read_text(encoding='utf-8')[-1500:] if prev_path.exists() else ''
    ctx = asyncio.run(asm.assemble(ch_num, beat, chars, world, narrator_guide=VOICE, last_emotion='紧张'))
    print(f'Ch{ch_num} graph: {len(ctx.graph_insights)}c')
    gen = Generator(config, gw, prompts)
    result = asyncio.run(gen.generate_chapter(
        chapter_num=ch_num, beat=beat, characters=chars, world=world,
        last_emotion='紧张', recent_chapters=recent, narrator_guide=VOICE,
        temperature=0.95, segmented=False, chapter_type='normal',
    ))
    gen.save_chapter(result)
    print(f'Ch{ch_num}: {result.word_count}w')
print('Done')
