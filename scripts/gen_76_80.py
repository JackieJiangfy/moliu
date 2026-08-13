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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。悬念推进。'

beats = {
    76: '渡劫基金兑现后的第三天，银行里前所未有的安静——没有鬼上门讨债，没有财政司的人来敲门。老白说他活了三百多年头一回觉得这办公室太安静了。沈夜说你是闲得慌——去把柜子底下那箱旧文件整理一下。老白不情不愿地去搬箱子，搬到底层的时候发现了一个铁盒——不是银行的，是沈万通的私人物品。铁盒里是一张照片、一把钥匙、和一份死亡证明。死亡证明上的死因不是执念反噬——是谋杀。签名的法医名字沈夜不认识。老白认识：那是你爹生前的私人医生。',
    77: '沈夜去找赵铁面查那个法医——赵铁面看了名字很久，说我以为这个人已经死了。沈夜问他是谁。赵铁面说他是地府最早一批法医，专做亡灵尸检。十九年前这个法医突然辞职失踪——没人知道他去了哪。沈夜问为什么辞职。赵铁面说他最后一份尸检报告被人篡改了。那份报告的编号跟你爹的死亡证明编号一模一样。',
    78: '赵铁面拿出了一份旧档案——那个法医辞职前寄给他的最后一封信。信里只有一行字：沈万通的死亡证明是假的。他不是病死的，也不是执念反噬——他身上有七处伤口，每一处都对应一条他生前正在追查的债务链。有人不想让他查下去。沈夜看着那行字很久。然后问赵铁面：这个人还活着吗。赵铁面说我不知道。但他有个女儿——在地府第七层。如果你能找到她，你就能找到真相。',
    79: '地府第七层不是活人该去的地方——那是被地府司法体系遗忘的角落，关着最古老的债务鬼。沈夜带着老白和孟小鱼下去。第七层的入口在忘川河底——要过一个摆渡。摆渡人是个老鬼，看了一眼沈夜说活人不渡。沈夜说渡。老鬼说凭什么。沈夜从兜里掏出那台老验钞机放在船头。屏幕亮了一下。老鬼看了很久说你爹当年也是这么上船的。上船之前他跟我说了一句话——他欠的人命，总有一天他儿子会来还。沈夜说他欠的命——我现在还。摆渡人把船推了出去。',
    80: '他们在第七层找到了法医的女儿——她在这里被关了十九年，罪名是颠倒是非，私改公务文书。她说她父亲没有篡改尸检报告——他是被人逼着改的。真正的尸检报告原稿藏在城隍庙地下一层——她父亲去投案之前复制了一份寄存在那。那份原稿上写了沈万通的真正死因和凶手名字。沈夜问她凶手是谁。她说我不知道名字——但我爸在原稿上画了一个标记。那个标记代表的是地府财政司。',
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
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (77,78): m['key_characters'].append('赵铁面')
    if ch_num == 79: m['key_characters'].append('孟小鱼')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')

print('Done!')
