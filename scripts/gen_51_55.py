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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。悬念推进，每章结尾验钞机亮一次。'

beats = {
    51: '蒋副司长的人来了——不是审计，是查封。他拿着沈万通当年签的承诺书，要求冻结亡灵银行全部资产。沈夜把经营报告、审计通过书、渡劫基金协议摊在桌上说我爹签的承诺书前提是银行无法正常经营——你看清楚了，正常两个字怎么写。蒋的律师团翻了一下午文件。临走时蒋的秘书在门口停了一下：沈先生，副司长让我转告你——你爹当年的那笔资产，不是只有你一个人在找。',
    52: '沈夜让孟小鱼查蒋副司长跟沈万通的历史。孟小鱼从地府档案室调出一份旧文件——十九年前，蒋是沈万通手下最年轻的审计员。沈万通发现了他的账有问题，但没有举报。沈夜问为什么没举报。孟小鱼说你爹给过他一个选择：要么自己辞，要么帮他做一件事。蒋选了帮他做事——把一笔资产从地府财政系统里彻底抹掉。那笔资产，就是渡劫基金的前身。',
    53: '老白翻出了一本从未见过的账本——封面没有字，里面全是符号，不是数字。沈夜看了半天认不出来。老白说你爹的暗账——他怕人偷看，用他自己编的符号记的。沈夜说你认得吗。老白说认得一部分——这是你爹教我的。剩下的只有他认识。沈夜让老白把认得的部分翻译出来——全部指向同一个地方：城隍庙地下二层，第三号储物柜。',
    54: '沈夜和老白去了城隍庙地下二层。储物柜里只有一样东西——一台跟银行里那台一模一样的验钞机。同样是墨绿色，同样老旧，但屏幕亮着不同的字：资产托管协议——签约方沈万通，托管方城隍庙地府分行，托管内容：312万客户原始存款凭证的备份密钥。沈夜把第二台验钞机抱回银行。两台机器放在一起的时候，屏幕同时亮了。48%跳到了62%。',
    55: '两台验钞机并排放在柜台上，屏幕上的数字同步跳动——62%。老白说这两台机器是你爹亲手做的。第一台验钞票，第二台验人。第一台给你了，第二台他一直锁在储物柜里——等你把坏账处理到过半，第二台才启动。沈夜问还有多少台。老白说不知道。你爹只跟我说过一句话：小夜什么时候找到第三台，什么时候就不用还债了。',
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
