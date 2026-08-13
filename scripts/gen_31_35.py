"""Generate Chapters 31-35"""
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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。悬念推进，每章结尾留钩子。'

beats = {
    31: '验钞机申请者未知提示亮了一整天。沈夜试了三次查不到身份——系统拒绝。老白说你爹留的后门被审计协议覆盖了。孟小鱼来电：周正邦让你去财政司档案室。沈夜去了。周正邦抱出一个锈迹斑斑的铁皮箱子——沈万通亲启，封存十九年。',
    32: '铁皮箱里是一摞手写信。沈万通申请注销亡灵银行法人资格——把债务转为个人债务。全被驳回——除非法人死了才能剥离。周正邦说沈万通不是病死的，是被执念杀死的。有人盯上他很久了。',
    33: '周正邦翻到最后一页——沈万通死前三个月的流水。七次扣款，同一个扣款方：地府司法司执念清算科。扣款理由执念质押扣款。沈夜想起倒计时还剩不到20小时。归零后会发生什么——没人告诉他。',
    34: '沈夜把铁皮箱搬回银行。老白把所有信件摊开。孟小鱼调出沈万通死亡档案——死因执念反噬。老白说你爹最后几年在查一件事：三千万坏账里有一笔不是坏账，是被人故意做成的坏账。最后一封信落款不是沈万通——是赵铁面。',
    35: '赵铁面的信只有一行字：那笔资产接收人登记在你名下。你活着它永远是坏账。你死了它才浮出水面。沈夜明白了——他爹跑路不是躲债，是用自己的命逼出那笔资产。倒计时归零。验钞机亮起最后一行字：资产已解冻。接收人沈夜。然后暗了，重新亮起——欢迎回来法人。',
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
        chapter_type='climax' if ch_num >= 34 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'Ch{ch_num}: {result.word_count}w')
print('Done')
