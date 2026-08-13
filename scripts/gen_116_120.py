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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。终局高潮，情感爆发。'

beats = {
    116: '沈夜拿着从042号箱里取出的蒋继先财务记录，带着老白直奔财政司大楼。他没有偷偷摸摸——他直接走了正门，在前台登记了访客。前台问他找谁，他说找蒋副司长。电梯上了十二层。走廊很长，灯管坏了一半。他走到走廊尽头的办公室门口，门牌上写着"蒋继先 副司长"。门没锁。他推门进去，办公室里空无一人。他走到办公桌前，按他妈说的——抽屉夹层在右手边从上往下第二个。他把手伸进去摸了一圈，摸到一张门禁卡和一把保险柜钥匙。桌前挂着一幅字——"公生明廉生威"。他取下那幅字，后面露出一个嵌入式保险柜。钥匙插进去，门禁卡刷过，柜门弹开。里面是一摞暗账原始单据，从1978年一直到2021年。最上面压着一张照片——沈万通和韩济川的合影，背面有韩济川的字：此人知道太多，不能留。',

    117: '沈夜正要把单据装进背包，身后的灯全亮了。蒋继先进来了，身后跟着两个西装革履的地府保安。他没看沈夜手里的东西，先看了看桌上那幅被取下来的字，又看了看敞开的保险柜。然后他不紧不慢地走到办公桌后面坐下来，抬头看着沈夜：东西你看到了。现在你打算怎么办。沈夜攥紧手里的单据没说话。蒋继先说你拿了证据就走不出去——我这扇门外面有十二个保安。你走出去，他们会抓你。你不走——他指了指沈夜怀里的验钞机——你爹那台破机器救不了你。沈夜把验钞机放在桌上。屏幕上正闪着一行字：实时记录已上传亡灵银行云端服务器。蒋继先盯着那行字看了很久，脸色的变化沈夜看得很清楚——先是不信，然后是惊，最后是一种很冷的平静。他说你爹当年也想过用这台机器对付我。但他没来得及。',

    118: '沈夜说那现在聊聊。蒋继先沉默了一会儿然后让两个保安出去了。他说你想知道什么。沈夜说我爹怎么死的。蒋继先说你爹不是被杀的——他是自己选的。韩济川临死前留了一份遗嘱说沈万通手里有证据能毁掉整个财政司让他处理掉。遗嘱递到我手里的时候韩济川已经咽了气。我拿给你爹看了。你爹看完说了一句话：让他杀。我不跑——我跑了，那份遗嘱就会变成追杀我儿子的令。蒋继先顿了顿：所以你爹跟我做了个交易。他把所有证据锁进042号箱交给我保管，作为交换，我烧了那份遗嘱。然后他去临江墓园给自己挖了个坟。沈夜的声音有点哑：你看着他死的。蒋继先说不是我看着他死——是我帮他。他说他活够了，他要用自己的命换你活。我只是答应了他。',

    119: '沈夜在蒋继先的办公室里坐了很久。他不是在哭，也不是在沉默，他是在算——算他爹这辈子做了多少笔交易。跟顾长明做，跟钟国良做，跟蒋继先做。每一笔交易都是用自己换别人。办公室的钟走了将近一个钟头。然后沈夜站起来说你说的这些我都记下了。蒋继先说你记下有什么用。沈夜说你刚才说的话这台验钞机全录了——实时上传。蒋继先的脸色终于变了。沈夜说你别怕，我不是要把你送进大牢——我是要你把该认的认了。韩济川的洗钱链运行了四十年，你接手了十九年。你把这十九年的暗账全部交出来，自己去审计局自首。剩下的事，让审计局判。蒋继先看着他说如果我不呢。沈夜把验钞机翻过来给他看屏幕——屏幕上显示传输进度：95%。他说十分钟前就已经传完了。现在这些单据和录音在三个服务器上各有一份备份——亡灵银行、审计局、地府法院。你觉得你能删得过来？',

    120: '三天后。沈夜坐在亡灵银行办公室里，面前摆着那台验钞机。它已经亮了整整三天了——从蒋继先自首那天开始，屏幕上不断滚动着地府各大部门的处理进度。财政司自查确认书已签。钟国良三个暗账账户已被冻结。蒋继先移交审计局。曹桂兰案已重新立案——赔偿金从冻结账户中支出。陈秀莲已于昨日收到地府民政局转交的一百二十万功德币赔偿款。最后一条更新是今天早上跳出来的——顾长明辞去财政司司长职务，由副司长暂代。沈夜靠在椅背上看着这些字一个一个跳过去。老白飘在他身后说你把自己整没工作了。沈夜笑了笑说我本来就是继承的。老白问那你接下来干嘛。沈夜说还没想好——先把欠你的工资结了吧。他把验钞机的电源拔了，屏幕暗下来。办公室安静了一会儿。然后他拿起手机给赵兰打了个电话：妈，事情办完了。来看看我爸吧。',

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
    if ch_num in (116,117,118,119): m['key_characters'].append('蒋继先')
    if ch_num in (118,119): m['key_characters'].append('沈万通')
    if ch_num in (119,): m['key_characters'].append('顾长明')
    if ch_num == 120: m['key_characters'].extend(['沈万通','赵兰'])
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
