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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。悬念推进高潮。'

beats = {
    106: '验钞机输出了三本暗账的完整历史流水。沈夜花了整整一个通宵整理数据——三千年的洗钱记录，从第一笔到今天，密密麻麻像蚂蚁排队。他发现这些账户不仅是洗钱工具——它们构成了一整套影子银行体系，跟亡灵银行平行运转的、完全不受监管的结算网络。亡灵银行只覆盖地府和阳间的功德币流通，但这套影子系统覆盖了阴阳两界所有被洗掉的资金——规模大概是亡灵银行的十几倍。老白飘过来看屏幕说你现在知道为什么你爹说碰一下就得出事了吧——你碰的不是一个人，是一个系统。沈夜盯着屏幕上一行高亮的记录——最近三年有一笔异常转账，金额大到不像洗钱，像是转移资产。他点了进去。',
    107: '那笔转账发生在三年前，金额折合功德币八十七亿。沈夜顺着账本往下查——资金来源是地府财务部一个代号叫"天字四号"的清算通道，资金经过三个死人账户的层层转手，最终流入了阳间一家公司。公司名叫通远实业，注册地在临江。沈夜让孟小鱼帮他工商查档——孟小鱼隔了半小时回了一条语音，声音很怪：沈夜，这家公司的法人代表叫沈万通。沈夜把那条语音听了三遍。他放下手机，看着屏幕上那个名字，脑子里一片空白。他爹的名字——他死了十九年的爹——出现在洗钱链的最末端。老白凑过来看了一眼屏幕。他看了很久，然后说了一句话：三年前，你爹已经死了。',
    108: '沈夜重新梳理了那笔八十七亿转账的时间线。2021年——他爹2004年失踪，按地府的时间算已经死了。一个死人不可能注册公司。他让赵铁面帮他调通远实业的工商档案，拿到注册文件的扫描件。他把注册文件上的签名跟沈万通的笔迹做了比对——纸面上的签名写得很像，但墨迹的力道不对。他爹写字的时候绞丝旁永远比右边大，而这个签名写得太"正常"了。他对老白说这不是我爹签的。老白问他打算怎么查。沈夜说他注册的时候总要人脸识别或者线下验身份证——顺着注册渠道往回追。他追到临江一家代理注册公司。电话打过去，那头是个老头：你说通远啊——我记得，当年有个中年人戴着墨镜来办的，拿的沈万通的身份证。沈夜问他长什么样。老头说记不太清了，但他签字的时候我注意到一个东西——他左手缺了一根手指。',
    109: '沈夜挂了电话。老白看着他问怎么了。沈夜说钟国良左手缺了一根无名指——你之前说过，是他三千年前对账事故中被算盘夹断的。他用了我爹的名字注册公司，用我爹的名义走那八十七亿。老白沉默了很久说他想干嘛。沈夜说他想把整个洗钱链的终端安在我爹头上。万一哪天事情败露，追查的人追到最后一步会发现——所有的资金最终受益人写着沈万通。死人是不会辩解。沈夜从老白那翻到钟国良当年留下的一个座机号。他想了很久拨了过去。电话响了五声接通了。那头是个苍老但很稳的声音：你是沈万通的儿子。我等这个电话等了很久了。沈夜握着电话的手收紧了。',
    110: '沈夜说你知道我会打。钟国良说当然——你动了三个账户，触发了追踪程序。那台验钞机是你爹花十七年编写的，专门盯着我。我等了十九年想知道他到底留没留给你——你动了，说明他留了。沈夜说你用我爹的名字注册通远实业。钟国良说是的。你爹欠我一笔账。他活着的时候没还清，所以我用他的名字继续收。沈夜说他已经死了十九年了。钟国良的声音平静得像在念天气预报：我知道。他死之前来找过我，说他有个儿子才七岁，让我别动他。所以我这十九年没动你——直到你动了我的账户。电话挂断。沈夜握着手机站在办公室中间。他第一次听懂了——他爹当年去找钟国良不是去算账求公道，是去求钟国良别动自己的儿子。老白说那天他出来的时候像被抽了魂，不是因为输了账，是因为他为了保你，向钟国良低了头。沈夜看着验钞机上还在滚滚输出的暗账数据。他说我爸用他的尊严换我活十九年——那我用这十九年换他的账算完。老白问你想怎么办。沈夜说把这些全部公开。',
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
        temperature=0.95, segmented=False,
        chapter_type='climax',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (106,107,108): m['key_characters'].append('钟国良')
    if ch_num in (107,108): m['key_characters'].append('沈万通')
    if ch_num == 107: m['key_characters'].append('孟小鱼')
    if ch_num == 108: m['key_characters'].append('赵铁面')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
