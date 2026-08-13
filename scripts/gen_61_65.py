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
    61: '沈夜去了市博物馆。铜镜被收在库房里——要提出来得走层层审批。他在柜台前填了四张表，排了三个窗口，最后被告知需要副馆长签字。副馆长姓秦，四十多岁，戴金丝边眼镜，坐在办公室里翻文件。沈夜把周万贯的委托书放在桌上。秦馆长看了一眼说这面铜镜是馆藏文物——不能外借。沈夜说我不借——我看一眼就行，我帮一个老人了却心愿。秦馆长说你帮老人，谁帮你。沈夜说他。他从口袋里掏出验钞机放在桌上。机子屏幕亮了一下，映出秦馆长脸上闪过的一点惊讶。秦馆长：你是沈万通的儿子。沈夜：你认识我爸。秦馆长：他欠我一面镜子。',
    62: '秦馆长说十九年前沈万通来博物馆借过这面铜镜——说要帮一个客户做资产评估。借了三天，还回来的时候镜面多了一道裂纹。从此博物馆的文物外借条例加了一行字：沈万通除外。沈夜说我还。秦馆长说你拿什么还。沈夜说我不是我爸——我不借。我就在库里看。你锁着门，我隔着玻璃看。我看完就走。秦馆长摘下眼镜擦了擦说你是第一个说自己不是你爸的人。沈夜说因为我不是。秦馆长站起来说你给我三天时间，我帮你把铜镜从库里提出来——但只能看一眼。沈夜问条件是什么。秦馆长说你帮我做一件事。沈夜说什么。秦馆长说我爸的墓被盗了。盗墓的卖了一件随葬品到黑市。你帮我要回来。',
    63: '随葬品是一枚铜印——刻着秦家老祖宗的名字。沈夜在黑市找到了卖家——一个专收出土文物的老鬼。老鬼说这印我买来花了八百功德币，现在你要拿走，得加价。沈夜说我没钱。老鬼说那你拿什么换。沈夜从口袋里掏出一个小本子——是他自己的银行存款记录。他撕下一张纸说这是我的名字。亡灵银行法人沈夜。你拿着这张纸——以后你来银行找我，我不收你利息。老鬼接过纸看了半天说你这签名值不值八百功德币。沈夜说我不知道。但我知道我爸的签名三千年前值三百阴德——他用了二十年还清。我不比他。但也差不多。',
    64: '沈夜把铜印交给秦馆长。秦馆长把铜镜从库里提出来，开了一个展柜，隔着玻璃让沈夜看。沈夜拍了几张高清照片，发给了周万贯的孙子。孙子回了一条消息说真的很漂亮。谢谢。沈夜把消息截屏发给周万贯。周万贯说够了。他拿出了那块碎片。沈夜接过去的时候手指碰到碎片边缘——冰凉。碎片在验钞机扫描口上贴了一下，屏幕上的数字跳了。从62%跳到63%。第二块碎片——来自一个他不认识的名字。备注栏只有一行字：此人已投胎。请查生死簿。',
    65: '沈夜去城隍庙查生死簿。那名客户叫陈老四，生前是个木匠，死后投胎四次，每一次都出生在同一个村子——为了照顾他生前没盖完的那栋房子。沈夜找到第五世——他现在是个七岁的孩子，在南方某个小镇上读小学。沈夜没有去找他。他在碎片备注栏里加了一行字：此人已投胎。碎片继承权转至其后代。然后让孟小鱼把这块碎片通过地府渠道寄过去——不是催债，是还钱。他爹欠的，现在还。验钞机没响。但沈夜觉得那数字靠他自己也会涨的。',
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
