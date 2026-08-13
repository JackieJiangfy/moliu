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
    101: '沈夜回到办公室，把那台老录像机接上电源。042号箱里的录像带他拿回来了——一盘老式VHS带子，外壳发黄，标签上是他爹的笔迹：给沈夜。他把带子推进录像机，屏幕亮了。沈万通坐在镜头前，四十多岁，穿着那件沈夜记忆中永远没换过的灰夹克，背景是这间办公室。他对着镜头说：儿子，你要是看到这个，说明我没了。你听着——042里的东西不是用来翻盘的，是用来看清一件事的。洗钱链的真正主使不是顾长明。顾长明是他岳父韩济川推到前台的。韩济川当了十九年财政司司长，退下来之前把整条洗钱链交给了顾长明。但韩济川已经死了——真正还在运作这条链子的人，是他当年的副手，叫钟国良。沈万通顿了一下说钟国良现在是地府财务部的一把手，管着整个功德币清算系统。他手上有一本暗账，记录了三百年间所有被洗掉的功德币流向。沈夜按下暂停，盯着屏幕上他爹的脸，半晌没动。',
    102: '沈夜把录像给老白看了。老白看完之后很久没说话，算盘珠子一颗都没拨。然后他说钟国良这个人他知道——三百年前他是地府财务部的记账员，后来一路爬到了部长。老白说你爹当年跑路之前见的最后一个人就是他。沈夜说你怎么知道。老白说因为我当时就在门外。你爹让我站在外面别进去，说他跟钟国良有笔账要算。我等了将近一个时辰，你爹出来的时候脸色白得像纸。我问他怎么了，他只说了一句话——别跟任何人说我来过这儿。沈夜看着老白说你瞒了我这么多年。老白说不是你爹不让说——是我不知道该怎么说。你爹那时候的样子，像被人抽走了魂。沈夜沉默了一会儿，然后顾长明打来了电话。他的声音很沉：沈夜，今天有人来财政司调了你爹当年的全部档案。我问了是谁——调令上没有署名。你小心点。',
    103: '沈夜决定去找钟国良。他查到钟国良的办公室在地府财务部十八楼。第二天一早他坐地铁过去，到了十八楼发现那层楼正在装修——工人说这层已经封了三个月了。沈夜觉得不对劲，打电话给赵铁面让他查钟国良的调动记录。赵铁面花了半天查到一条信息：钟国良三个月前被调离了财务部，调令上写的去向是地府特别事务办公室——赵铁面说这个办公室他查不到任何信息，连编制表上都没有。沈夜说我爹当年查的就是这个部门的运作方式。赵铁面说沈夜你听我一句——别再往下查了。沈夜说来不及了。他挂了电话回到银行，发现办公室的门虚掩着。里面被翻过——抽屉全拉开，文件散了一地。老白坐在角落的椅子上说他们来了三个人，戴着手套，什么都没拿。沈夜知道这不是盗窃——是警告。他看了一眼验钞机，屏幕亮着一行红字：002号保险箱状态异常，有人尝试访问。',
    104: '沈夜打开002号保险箱检查。夹层里的文件被人动过——沈万通留下的那些手稿、信纸、曹桂兰的目击证词复印件，全部被翻过，但一件不少。对方在找东西。老白说他们是在找那盘录像带。沈夜说录像带在042里，他们打不开。老白说所以他们才来翻——他们不知道录像带在哪，但他们知道存在这样东西。沈夜重新坐回桌前，把录像带重新看了一遍。他发现沈万通在录像最后几秒做了一个手势——手指不自然地指了一下桌上的相框。相框里是沈夜七岁的照片。他爹在录像里说如果你看到这，儿子，你比你爹聪明。沈夜盯着那个手势看了十几遍，然后站起来走到书架跟前。书架上摆着他小时候那张照片——七岁的沈夜站在办公室门口，穿一件大两号的校服。他把相框拿下来，翻开背面。照片后面粘着一张泛黄的纸，折得四四方方。',
    105: '沈夜打开那张纸，上面是他爹密密麻麻的铅笔字。抬头是四个字：钟国良账。下面列了三行数字——都是亡灵银行的账户编号。沈万通在旁边用铅笔批注了一行小字：钟国良在亡灵银行开了三个秘密账户，用的都是死人的名字。这些账户走的是亡灵银行的结算通道，不走地府财政部——所以没人能查得到。你手里的那台验钞机，我用它追踪了这些账户十七年。如果你能把这三笔账对平了，钟国良就跑不掉。沈夜把纸放在桌上，看着那三串数字。老白凑过来看了一眼说他用死人的名字开户——那这些账户的持有人都是谁。沈夜说查一下。他打开那台老电脑，输入第一个账户编号。屏幕上跳出一个名字——周翠英。死于1964年，享年六十一岁，生前职业：家庭妇女。沈夜看着那个名字沉默了一会儿。然后他查第二个账户——刘根生，死于1967年，码头搬运工。第三个——陈福来，死于1971年，退休小学教师。三个死人。三个跟洗钱链毫无关系的人。沈夜说他把这三笔账做平了就等于把钟国良的证据做全了。老白说你想好了吗——做平了，他就能顺着账户反查到你。沈夜说我知道。他把验钞机搬过来放在桌上，把那三个账户编号输了进去。验钞机亮了，屏幕上跳出一行他从未见过的进度条：暗账追踪启动。',
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
        chapter_type='climax' if ch_num >= 103 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (101,102,104): m['key_characters'].append('沈万通')
    if ch_num in (102,103,105): m['key_characters'].append('钟国良')
    if ch_num == 102: m['key_characters'].append('顾长明')
    if ch_num == 103: m['key_characters'].append('赵铁面')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
