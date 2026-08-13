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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。收官终章，情感落地，节奏从容不赶。'

beats = {
    121: '沈夜开车载着赵兰上了临江墓园的山路。车停在墓园门口，母子俩沿着石板路往上走。到了沈万通的墓前——那块碑还是歪的，旁边的柏树还是歪脖子。赵兰站在墓前很久没动。她从口袋里掏出一张叠得四四方方的纸放在墓碑上——是一张1987年的结婚照，背面已经泛黄。她说：万通，我来了。沈夜蹲在墓旁把043号箱重新埋好——里面放了他爹那本日记的复印件和他七岁那张照片。他埋完之后站起来，发现赵兰在看他。她说你爹留给你的那封信呢。沈夜从怀里掏出一个牛皮纸信封——是他在043号箱日记最后一页找到的。封面写着"赵兰亲启"。他递给他妈。赵兰拆开信看了很久。然后她把信纸贴在胸口，眼泪终于掉下来。她说了一句话：你爹说他不怪我——他说他这辈子最对不起的人是我，但他死之前最后悔的事是没来得及跟你吃一顿火锅。沈夜愣了一下然后笑了——不是平时那种吊儿郎当的笑，是眼睛红红的但嘴角在往上扯。他说那他确实欠我一顿饭。',

    122: '从墓园回来的路上，沈夜的手机又响了——还是那个号码。这次他接了。对方是个老头，声音沙哑但中气十足：你爹当年帮我平过一笔账。我欠他一条命。后来他托我一件事——让我在他死后第十九年给你送一样东西。现在期限到了。沈夜问你是谁。老头说我姓周，叫周正邦。以前在财政司干过——是你爹唯一信得过的审计官。你爹跑路之前把他手上最要紧的一样东西寄存在我这。沈夜把车靠边停下，问他什么东西。周正邦说：你爹在亡灵银行成立的第一天存了一笔钱，不是功德币，是一份保险——保险的受益人是你的名字。这么多年我一直替他交保费。明天这笔保险到期。你有两个选择——一次性提现，或者继续存。沈夜问金额多少。周正邦说了一个数字。电话那头沈夜沉默了将近十秒。赵兰在旁边看着他觉得不对劲，轻声问怎么了。沈夜把电话挂了，看着窗外说了两个字：他爹的。',

    123: '第二天一早沈夜去了周正邦说的地址——城隍庙后面一家做纸扎的老店。周正邦坐在轮椅上，头发全白了，但眼神很亮。他从怀里掏出一份保单——纸张已经发黄发脆，上面盖着亡灵银行的公章，日期是1987年4月3日。签单人：沈万通。被保人：沈夜。保单内容：沈万通从亡灵银行成立首日起每月缴纳功德币二百元，缴纳期限十九年。赔付条款只有一句话——若本人身故，所有已缴保费连本带息一次性赔付予沈夜。赔付金额栏写了一串数字。沈夜数了三遍——八十七亿功德币。他抬头看周正邦说你搞错了吧。周正邦说没错。你爹借钟国良的通道保管的那八十七亿不是洗钱链截下来的赃款——是他每个月二百二百攒下来的保费。他查洗钱链查了十九年，真正截下来的东西不是钱，是证据。那八十七亿是他用自己的钱一笔一笔存给你。沈夜拿着那份保单手一直在抖。他说他每个月省二百块钱存了十九年给我。周正邦说你爹那个人——他这辈子没给自己留过一分钱。',

    124: '沈夜走出纸扎店的时候天在下小雨。他站在门口很久没动。老白的电话打过来——你在哪呢，刚才赵铁面来过了，说审计局那边昨晚上把蒋继先的案卷全调走了，顾长明辞职的事也在系统里公示了。沈夜说知道了。老白顿了一下问你怎么了。沈夜说我爹留了一样东西给我——一份保险。老白问多少钱。沈夜说八十七亿。电话那头算盘珠子稀里哗啦响了一阵然后停了。老白说那是银行首日那天，你爹跟我说他想存一笔钱，我说你连午饭都省两顿的人存什么钱。他说存给我儿子的。我问他怎么存的。他说每个月从自己伙食费里挤。沈夜握着手机靠在纸扎店门口，雨水顺着屋檐往下滴。他说老白你工资翻倍发。老白说不行不行翻倍太夸张了——那就翻两倍。沈夜说成交。',

    125: '一个月后。城中村那条巷子还是老样子——炒菜味、棋牌室的麻将声、晾衣绳上的旧衣裳。亡灵银行的办公室也没怎么变，就是桌上多了一台新电脑，墙上那条裂缝被沈夜用腻子糊上了。老白坐在柜台后面拨算盘，搪瓷罐子里功德币哗啦啦响。门上贴了一张新告示——亡灵银行即日起正常营业，新开户免首年管理费，老客户利息翻倍。落款是"沈夜"。下面是赵兰补了一行字：茶水自取。沈夜蹲在墙角整理保险箱。001号、002号、003号——003他一直没开过。今天他打开了。里面不是账本不是保险单不是信——是一张全家福。他爹抱着七岁的他，他妈站在旁边，三个人站在这间办公室门口。照片背面是他爹的字：这一间屋，替你守了十九年。现在交给你了。沈夜把照片放在验钞机旁边。验钞机亮了一下，屏幕上跳出一行字——所有保险箱状态更新。001：正常。002：正常。003：正常。末了还有一行小字，是他爹的笔迹——都平了，儿子。关灯吧。沈夜看着那行字看了很久。然后伸手把验钞机的电源键按下去。屏幕暗了。他站起来走到门口，老白的声音从身后传来：明天还上班？沈夜回头看了一眼那间屋子——货架上摆着他爹的旧书，桌上那台老验钞机安安静静地待着，墙上的裂缝被腻子糊得不太平整但好歹不漏风了。他说：上。门在他身后轻轻合上。',

}

for ch_num, beat in beats.items():
    gw = DeepSeekGateway(config)
    prompts = PromptManager(config)
    asm = StructuredAssembler(config)
    prev_path = Path(f'output/chapters/第{ch_num - 1}章/正文.md')
    recent = prev_path.read_text(encoding='utf-8')[-1500:] if prev_path.exists() else ''
    print(f'Ch{ch_num} graph:', end=' ')
    ctx = asyncio.run(asm.assemble(ch_num, beat, chars, world, narrator_guide=VOICE, last_emotion='感动'))
    print(f'{len(ctx.graph_insights)}c' if ctx.graph_insights else 'FAIL')
    gen = Generator(config, gw, prompts)
    result = asyncio.run(gen.generate_chapter(
        chapter_num=ch_num, beat=beat, characters=chars, world=world,
        last_emotion='感动', recent_chapters=recent, narrator_guide=VOICE,
        temperature=0.95, segmented=False,
        chapter_type='epilogue' if ch_num >= 124 else 'climax',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (121,125): m['key_characters'].append('赵兰')
    if ch_num in (121,123,124,125): m['key_characters'].append('沈万通')
    if ch_num in (122,123): m['key_characters'].append('周正邦')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
