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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。悬念推进。'

beats = {
    66: '沈夜回到银行，把三块碎片摆在桌上。验钞机屏幕停在63%——距离100%还有三十七块。老白说按这个速度你得干到明年。沈夜说明年也行——我还没交明年房租。孟小鱼打电话来：蒋副司长那边有动作了——他在黑市放出消息，说他手里有十块碎片。条件是沈夜亲自去拿。老白说这是陷阱。沈夜说是——但陷阱里有十块碎片。我去。',
    67: '蒋副司长约在财政司顶楼会面。沈夜带着老白上去——电梯门开的时候，蒋坐在长桌尽头，面前摆着一个木盒。盒子打开，十块碎片整齐排列。蒋说你要碎片，我要渡劫基金的托管权。沈夜说不行。蒋说那就算了。沈夜坐下了。他打开手机播放了一段录音：十九年前，你帮他抹掉了那笔资产。你以为录音丢了——没丢。在我这。蒋的脸变了。沈夜关掉录音把手机收起来：十块碎片，换我删掉这段录音。蒋沉默了很久。他把木盒推过来。',
    68: '沈夜抱着木盒走出财政司大门。老白跟在后面说你刚才那段录音真的假的。沈夜说假的——AI合成的。老白愣住了。沈夜说我在网上找了个AI语音合成软件，输了两句蒋副司长以前公开开会说的官话，生成了一段。他信了。老白说你疯了。沈夜说他不敢赌。他做了十九年副司长，最怕的就是年轻时候那点黑历史被翻出来。我不需要真的——我只需要他不敢赌。',
    69: '十块碎片入账。验钞机从63%跳到73%。老白把碎片一块一块铺在柜台上，对着灯光看了很久。其中一块碎片上刻着一个他认识的名字——顾三娘。老白的手指停在那个名字上。沈夜问是谁。老白说你爹生前帮过的一个女人——她丈夫欠了赌债要把女儿卖掉，你爹出钱替她还了。后来顾三娘死了——是自杀。她一直以为是你爹帮她是因为欠了她的钱。她不知道——你爹从来不记账。你爹帮她，是因为她长得像你妈。',
    70: '赵铁面深夜来访。他说蒋被你耍了之后不会善罢甘休——接下来他会动用财政司的权力吊销你的法人资格。沈夜说他有这个权力吗。赵铁面说有——如果他证明你伪造证据。那段AI录音是伪造的证据。沈夜说赌的就是他不敢翻这事。赵铁面沉默了一会儿说你跟你爹一个毛病——太相信别人不敢赌。你爹赌了一辈子，最后把命赌没了。沈夜说他输了是他的事。我没输过。赵铁面站起来说那你准备好——明天蒋会来封你的银行。',
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
        temperature=0.95, segmented=False,
        chapter_type='climax' if ch_num == 70 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'Ch{ch_num}: {result.word_count}w')
print('Done')
