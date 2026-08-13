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
    86: '沈夜用钥匙打开十九楼左边第三个柜子。柜子里不是文件——是一整面墙的保险箱，每个保险箱上贴着一个编号。编号从001到042。他一个个看过去。编号旁边标注着日期——最早的日期是二十年前，最新的是他父亲跑路的前一天。001号保险箱上贴着沈万通的笔迹：这是第一笔。他打开001号——里面不是账本，是一张照片。照片上是一个中年男人和一个年轻女子，站在一栋在建大楼前面。照片背面写着：顾长明与曹桂兰。曹桂兰，1962年生，1998年失踪。沈夜把照片放在桌上。他低头看着电脑屏幕,把“曹桂兰”输入系统。系统弹出一行字：查无此人。',
    87: '沈夜翻遍了001号保险箱里的每一页文件。曹桂兰的失踪案关联着一笔功德币洗钱记录——她生前是财政司的出纳，管着地府功德币与阳间货币的兑换账户。她的失踪时间正好是顾长明升任财政司副司长的那一年。沈万通在文件最后一页写了一段话：顾长明把曹桂兰的账户变成了他私人的洗钱通道。我查到了004号保险箱就查不下去了——他发现了，派人来警告我。沈夜打开002、003、004号。每一号都是一条洗钱链的证据。到042号的时候柜子空了。最后一格只有一行字：042在顾长明手里。',
    88: '沈夜带着001号保险箱的文件去找周正邦。周正邦看了很久说我认识曹桂兰——她是我当年的同事。沈夜问你知道她失踪了吗。周正邦说知道。但没人敢查。沈夜问为什么。周正邦说因为查她的那天就是你爹跑路的前一天——你爹查到了042号，042号里的东西跟顾长明无关。跟地府高层有关。沈夜说多高。周正邦说我不能说——但我可以告诉你042号保险箱里是什么。是你爹的遗嘱。不是遗产遗嘱——是自白书。你爹写了十九年的审计驳回记录，每一笔都有顾长明的签名。但他最后查到的不是顾长明——是顾长明背后的人。',
    89: '沈夜回到银行把042号保险箱的事告诉老白。老白说042号钥匙在你爹手里——他跑路的时候带走了。沈夜说那就是说找到他跑路那天带的东西就能找到钥匙。老白说对——但你爹跑路的时候什么都没带。沈夜说不对，他带了一样东西。他从抽屉里拿出那台老验钞机——他爹唯一留给他的东西。他把验钞机翻过来，底部的螺丝拧开，里面有一把很小的铜钥匙。沈夜把钥匙对准验钞机底部的锁孔——不是电源插孔，是一个极小的刻着数字的锁孔。钥匙插进042号锁孔。验钞机屏幕亮了。上面没有百分比。只有一行字。',
    90: '验钞机屏幕上的那行字是沈万通的笔迹录进去的。他说小夜如果你看到这行字说明你已经找到了042。042不是一份文件——是一段录像。录的是十九年前顾长明和一个更高层的人在一间会议室里的对话。这段录像可以证明整个功德币洗钱链的存在。我把唯一的拷贝存在这台验钞机里。我跑路之前把录像录了进去——因为不录下来的话，顾长明迟早会把它销毁。你爹最后说了一句话：小夜，录像别给别人看。看完之后你自己决定。你要是不想查了，把验钞机砸了，没人会知道你看过。你要是决定查——你去找一个人。那个人不是周正邦，不是赵铁面，不是蒋副司长。那个人叫曹桂兰的女儿。她没死。',
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
        temperature=0.95, segmented=False, chapter_type='climax' if ch_num == 90 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (87,88): m['key_characters'].append('周正邦')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
