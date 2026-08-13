"""Generate short story: 沈万通的最后一天"""
import asyncio, json, re
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

VOICE = ('沈万通视角，第一人称。他是一个骗了无数人的老骗子，但他骗的每一笔钱都是为了填亡灵银行的窟窿。'
         '他嘴欠，喜欢说反话，越是舍不得的时候越要装得无所谓。'
         '情感克制——不煽情，不说教，用动作和细节传递情绪。'
         '节奏从容，每段之间有呼吸感。')

beat = (
    '【故事背景】2004年。沈万通知道自己活不成了。韩济川的遗嘱已经到了蒋继先手里——上面写着"沈万通不能留"。'
    '他只有三天时间。这三天里他要做好几件事：给四岁的儿子写一封十九年后才会收到的挂号信、'
    '去求钟国良别动他儿子、在验钞机里录下最后一条消息、给自己挖一个坟。\n\n'

    '【开篇】沈万通坐在亡灵银行办公室里，面前放着一沓信纸。老白在柜台后面打算盘，不知道他要干什么。'
    '沈万通提起笔，第一行写了"小夜"两个字，然后停住了。他不知道该怎么跟一个四岁的小孩解释他接下来要消失十九年。'
    '最后他写了一封信，收件人写的是"十九年后的沈夜"。他把信装进地府挂号信专用的牛皮纸袋里，封口，贴上邮票，'
    '递给老白说：帮我寄出去。老白问寄给谁。沈万通说寄给我儿子——十九年后寄。老白愣了一下。沈万通说放心，地府挂号信可以定时投递，我填的日期是十九年后的今天。\n\n'

    '【中段一：见钟国良】沈万通去了钟国良的办公室。他带着验钞机和一份账本。钟国良坐在办公桌后面，'
    '沈万通把账本放在桌上——那是他截下来的洗钱链记录，记录了钟国良通过死人账户走账的全部流水。钟国良脸色变了。'
    '沈万通说我不是来威胁你的——我是来求你一件事。我有个儿子，今年四岁。我要你答应我，十九年内不动他。'
    '钟国良问那十九年后呢。沈万通说十九年后他长大了，能自己扛了。钟国良沉默了很长时间，然后问你能给我什么。'
    '沈万通把验钞机放在桌上说：这里面有一套追踪程序，专门盯着你的暗账。只要我活着，它就一直运行。我死了，它就停。'
    '钟国良说你在用自己的命换你儿子的命。沈万通笑了笑说：我的命不值钱。钟国良最后点了头。沈万通走到门口的时候，'
    '钟国良说了一句话：沈万通，你那台机器——你儿子十九年后会不会拿到它。沈万通没回头。他说：会。他比我聪明。\n\n'

    '【中段二：录最后一条消息】回到银行，老白已经被他支走了。沈万通一个人坐在办公室里，把验钞机接到电脑上，'
    '一条一条地录。他录了暗账追踪系统的启动密码、录了001号保险箱的状态监控程序、录了给儿子的第一行字——"欢迎回来，法人。"'
    '最后他录了一条消息，设置触发条件为"曹桂兰案结案"。他对着麦克风愣了很久，最终只写了两个字：续上了。'
    '他想再多写几句，但发现什么话都多余。续上了——他没查完的账，他希望有一个人替他续上。\n\n'

    '【中段三：临江墓园】凌晨四点，沈万通一个人开着那辆破面包车去了临江墓园。他在山坡后面选了一块地，'
    '从后车厢拿出铁锹和镐头，开始挖。挖了将近两个小时。天蒙蒙亮的时候，坑挖好了。他坐在坑边，'
    '从兜里掏出一根烟点上。他把娶赵兰时的结婚照从口袋里拿出来看了看——照片上的自己还很年轻，穿着白衬衫，'
    '赵兰扎着辫子，笑得很好看。他把照片翻过来，写了一行字：棺材本来就是给活人看的。然后把照片放进一个铁盒里，'
    '塞进坑底的砖缝——那是043号保险箱的位置。\n\n'

    '【尾声】蒋继先来了。他看着那个挖好的坑，看着坐在坑边抽烟的沈万通，半天没说出话。沈万通说你来早了，我再抽一根。'
    '蒋继先说我答应了韩济川。沈万通说我知道。蒋继先说你还有什么要交代的。沈万通想了想说：我儿子七岁，叫沈夜。'
    '以后他要是来找你——你别拦他。蒋继先没接话。沈万通把烟头扔进坑里，站起来拍了拍土，自己跳了下去。'
    '他躺在坑底看着灰蒙蒙的天，说了一句话：老蒋，你干活利索点，别磨磨蹭蹭的。\n\n'

    '【结尾】十九年后。一个叫沈夜的年轻人收到了地府寄来的挂号信。他拆开信，里面只有几行字——'
    '"小夜，合同这种东西，看也看不懂，签就完了。爸爸。沈万通。"年轻人看了三遍，骂了一句"这老东西"，'
    '然后签了字。他不知道这封信等了十九年才寄到他手里。\n\n'

    '【全篇尾注，单独一行】\n'
    '（本篇为《亡灵银行》番外短篇。沈夜继承银行后的完整故事，请搜索番茄小说《亡灵银行》或点击作者主页阅读长篇正文。）'
)

gw = DeepSeekGateway(config)
prompts = PromptManager(config)
asm = StructuredAssembler(config)

# Use world/character context but no chapter context
ctx = asyncio.run(asm.assemble(0, beat, chars, world, narrator_guide=VOICE, last_emotion='悲伤'))
print(f'Graph: {len(ctx.graph_insights)}c' if ctx.graph_insights else 'Graph: N/A (短篇)')

gen = Generator(config, gw, prompts)
result = asyncio.run(gen.generate_chapter(
    chapter_num=0, beat=beat, characters=chars, world=world,
    last_emotion='悲伤', recent_chapters='', narrator_guide=VOICE,
    temperature=0.95, segmented=True,  # Use segmented generation for longer output
    chapter_type='normal',
))

# Save to short story directory
out_dir = Path('output/short_story')
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / '沈万通的最后一天.md').write_text(result.content, encoding='utf-8')

wc = len(re.findall(r'[一-鿿㐀-䶿]', result.content))
print(f'字数: {wc}')
print(f'Saved to output/short_story/沈万通的最后一天.md')
