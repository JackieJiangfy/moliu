import asyncio, json
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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。悬念推进。'

beats = {
    91: '沈夜让孟小鱼查曹桂兰女儿的下落。孟小鱼翻遍了地府档案——曹桂兰失踪后她女儿被送进了福利院，后来被一对夫妻收养，改名换姓。收养记录上的新名字很普通，但孟小鱼多翻了一页发现收养她的夫妻是地府公务员。孟小鱼说这对夫妻的背景查不到——档案被人为清理过。沈夜说是顾长明的人。孟小鱼点头：他怕曹桂兰的女儿长大之后回来找他。沈夜说她今年多大了。孟小鱼算了算：四十二。跟你爸跑路的时候差不多大。',
    92: '沈夜找到了曹桂兰女儿的养父母——两个退休的地府公务员。老头开了门说我等了十九年有人来问。沈夜说你知道我会来。老头说沈万通跑路之前来见过我们一次——他让我们保护好那个孩子。沈夜问为什么你们要帮他。老头说我欠他一条命——他帮我太太还过一笔功德币贷款。沈夜说那她现在在哪。老头说她大学毕业之后去了南方，在一家小公司做会计。沈夜说会计。老头说对。跟你一样。',
    93: '沈夜坐火车去了南方。一个小城市的工业园区，一栋灰色的写字楼。他在三楼找到了那家公司的财务科。一个中年女人坐在工位前面，对着电脑屏幕上的Excel表格。沈夜站在门口看了她很久。她抬起头说你找谁。沈夜说我找曹桂兰的女儿。她手里的笔停了。她从抽屉里拿出一张照片放在桌上——照片上是年轻时候的曹桂兰。她说这是我妈。你怎么认识她的。沈夜说我爸认识她。我爸叫沈万通。她沉默了很久。然后说我知道这个名字。我妈的笔记本上记了它很多遍。',
    94: '她叫许薇。养父母给她起的名字。她从办公桌底下搬出一个纸箱子——里面是她母亲曹桂兰的遗物。笔记本、工作证、几张照片、一份手写的举报信。举报信上写的是顾长明利用功德币兑换账户洗钱的全部细节。许薇说我妈写这封信的时候我才七岁。她写完第二天就失踪了。沈夜把信翻到最后一页。他看到了他爹的名字——沈万通，证人。他爹不是查到这件事的人——他爹是目击者。举报信的落款日期是他爹跑路的前一周。',
    95: '沈夜把举报信复印了一份带回银行。老白看了很久说我认得这笔迹，曹桂兰。她出事之前来过银行找你爹。沈夜问他们说了什么。老白说她让你爹帮她保管一样东西，你爹答应了，他把一个信封锁进了002号保险箱。后来你爹跑路，那个信封再也没人动过。沈夜打开002号保险箱，里面还有一个夹层。夹层里有一个信封，封面写着沈万通收，寄信人曹桂兰。他打开信封，里面是一张结婚照，背面一行字：沈哥，如果我出了事，帮我告诉许薇，她妈没做错任何事。',
}

for ch_num, beat in beats.items():
    gw = DeepSeekGateway(config)
    prompts = PromptManager(config)
    asm = StructuredAssembler(config)
    prev_path = Path(f'output/chapters/第{ch_num - 1}章/正文.md')
    recent = prev_path.read_text(encoding='utf-8')[-1500:] if prev_path.exists() else ''
    print(f'Ch{ch_num} graph:', end=' ')
    ctx = asyncio.run(asm.assemble(ch_num, beat, chars, world, narrator_guide=VOICE, last_emotion='紧张'))
    print(f'{len(ctx.graph_insights)}c' if ctx.graph_insights else 'FAIL')
    gen = Generator(config, gw, prompts)
    result = asyncio.run(gen.generate_chapter(
        chapter_num=ch_num, beat=beat, characters=chars, world=world,
        last_emotion='紧张', recent_chapters=recent, narrator_guide=VOICE,
        temperature=0.95, segmented=False, chapter_type='normal',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (91,94): m['key_characters'].append('孟小鱼')
    if ch_num in (93,94,95): m['key_characters'].append('许薇')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
