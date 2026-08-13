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
    56: '地府黑市不在阴间——在阳间。每周三凌晨三点，城西废弃工厂的地下停车场。沈夜按赵铁面给的地址找到入口——一个穿着保安服的老头坐在折叠椅上，面前放着一个纸箱，纸箱上写着入场的条件不是钱——是拿一样东西来换。沈夜说我没东西。老头说你有——你身上有一台验钞机。沈夜把第一台验钞机放进纸箱。老头看了一眼说你进去了这台机器是你的入场费不退。沈夜说我知道。他进去了。',
    57: '黑市是个地下拍卖场。鬼魂、活人、地府公务员混在一起，没人问对方是谁。今晚的拍品是一块功德碑——碑上刻着沈万通的名字。起拍价三千万功德币。沈夜没有三千万。但他在台下看到了一个人——蒋副司长，坐在前排，手里拿着号牌。沈夜在最后一排坐下。旁边一个戴墨镜的老头转头看他：你爹当年也坐这个位置。每次来都不举牌——他是来盯着别人拍的。沈夜说那我也盯着。',
    58: '赵铁面派来的人是个年轻人，自称姓顾，是审计局的新人——但他知道黑市的每一条规则。小顾说沈万通的功德碑被拍了十九年了，每次都被蒋副司长的人拍走再转手卖掉。这块碑是沈万通用的命换的——他死之前把所有功德值注入功德碑，碑上每一个名字都是他欠过债的客户。沈夜问碑现在在哪。小顾说被拆了。拆成了三十八块碎片，分散在黑市各处。每一块代表渡劫基金的百分之一。',
    59: '沈夜回到银行，把黑市的情况告诉老白。三十八块碎片，三十八个百分点。他爹把他自己拆成了三十八份，每一份押在一个客户身上。老白说不是你爹拆的——是蒋副司长拆的。他以为拆了碑就能拆了渡劫基金。但他错了。你爹的功德碑跟功德币不一样——不管你拆成几块，只要有人把碎片拼回去，碑上的每一个名字都会恢复。沈夜说那就一块一块买回来。老白说你哪来的钱。沈夜说不用钱——我是碑上名字的继承人。碎片认的不是钱，是血。',
    60: '第一块碎片——沈万通名字的右下角，刻着白露两个字。碎片持有人是一个老鬼，八十多岁，生前是当铺老板。他说这块碎片我不卖。但我可以换——换你帮我做一件事。我孙子今年考大学，志愿填了金融。他爹他妈都是金融圈的，祖上也是。就我一个是当铺的。我想让他学点别的。沈夜说你想让他学什么。老鬼说学考古。我活着的时候收过一样东西——唐代的海兽葡萄纹铜镜，被博物馆收走了。你帮我把那面铜镜要回来，让我孙子看一眼真东西。沈夜说行。',
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
