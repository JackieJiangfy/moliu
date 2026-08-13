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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。高潮推进，节奏紧凑。'

beats = {
    111: '沈夜带着验钞机去了临江墓园。他没有先去柳河路——他觉得钟国良约在超市门口见面不靠谱。他要先确认一件事：他爹的坟里到底埋的什么。墓园管理处是个老头，翻了半天记录说沈万通的墓是十九年前一个叫钟国良的人出钱买的——连墓碑上的字都是钟国良选的。沈夜走到墓前，墓碑上的字很普通，但他注意到碑文底下刻了一行小字，格式像地府功德币的结算码。他犹豫了一下，把验钞机拿出来对着那行小字扫了一下。验钞机亮了，屏幕上跳出一行他从未见过的字：保险箱043号已激活。持有人沈万通。子账户继承人沈夜。指纹验证通过。沈夜盯着那行字——他爹把保险箱藏在了自己的坟里。',
    112: '沈夜从墓园借了工具。老白在一边念叨说你真要挖你爹的坟——这不合适吧。沈夜说他要是在里面那才不合适。他挖开墓穴，棺材里没有尸骨——只有一个小型保险箱，跟042号箱一模一样的外观，编号043。密码锁上的问题不是常规密码——屏幕上显示的是一行字：我儿子的名字叫什么。沈夜输入"沈夜"。锁开了。箱子里是他爹一本手写日记。日记从跑路那天开始记——第一页：今天把八十七亿转给了钟国良。这些年我一直在截洗钱链里的资金，攒了八十七亿，全部转给了钟国良让他用死人账户保管。他以为我在洗钱——其实我在用他的通道保护这笔钱。这笔钱是亡灵银行的准备金，没有它，银行三年就崩。钟国良到现在都不知道，那八十七亿的每一分钱都是我从他手里偷回来的。',
    113: '沈夜继续翻日记。沈万通的字越来越潦草，时间跨度从2004年一直到2019年——他在外面没死，活了十五年。日记里反复出现一个姓"蒋"的人。沈万通写道：蒋今天派人来搜过办公室，他们找不到043。043不在银行——在我死后会去的地方。沈夜翻到最后一页，是他爹死前记的。日期是2019年3月——他十九岁生日那天。上面就一句话：小夜今天十九了。银行的准备金够了。我可以死了。下面压着一张照片——他爹站在临江墓园这块碑前面，背后是没填土的墓穴。照片背面写：棺材本来就是给活人看的。沈夜看着那行字沉默了很久。',
    114: '沈夜把日记和照片装好带回银行。老白翻到"蒋"那个名字时脸色变了——他说蒋继先是地府财政司副司长，韩济川的女婿，顾长明的小舅子。韩济川死之前把洗钱链分成了两半，一半给顾长明管公开账，一半给蒋继先管暗账。顾长明这些年不肯查下去——不是因为他是主使，而是因为查到最后会查到自己的小舅子。沈夜说顾长明知道。老白说他知道但他下不了手。他老婆只剩这一个弟弟了。沈夜沉默了一会儿说：顾长明当年见死不救——不是不想救，是不敢救。救了我爹就要查蒋继先，查了蒋继先他老婆就没了。沈夜拿起手机打给顾长明。电话接通，他说了一句：顾司长，你小舅子的事，我要查到底。',
    115: '顾长明在电话里沉默了很久。然后他说：你查吧。这些年我一直等着有个人跟我说这句话。你爹当年最后一封信写给我的时候，我没办法回——因为我签字就等于亲手把自己老婆的弟弟送进去。我当了十九年财政司司长没动他一根汗毛。现在你来动——我不拦你。沈夜说我不需要你不拦我——我需要你帮我。顾长明问怎么帮。沈夜说我要蒋继先的财务档案。完整的——包括他在财政司内部经手的所有暗账的记录。顾长明说你这是要我叛变。沈夜说你不是叛变——你是平账。顾长明又沉默了。然后他说：明天早上你打开042号箱。沈夜挂了电话。老白问明天等着是什么。沈夜说不知道。第二天早上沈夜打开了042号箱——里面多了一沓文件。顾长明连夜放进去的。文件的第一页是蒋继先的履历表，旁边用红笔写着一行字：此人活着的每一天，都在替韩济川花死人钱。下面密密麻麻全是暗账记录。',

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
    if ch_num in (111,112,113): m['key_characters'].append('沈万通')
    if ch_num in (111,): m['key_characters'].append('钟国良')
    if ch_num in (113,114,115): m['key_characters'].append('蒋继先')
    if ch_num in (114,115): m['key_characters'].append('顾长明')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
