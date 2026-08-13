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

beat = '沈夜按法医女儿给的线索去城隍庙地下一层找尸检报告原稿。寄存处是个老鬼，说十九年前有人寄了一份文件放在最底层。沈夜取出来——是一份手写尸检报告。报告上写了沈万通的真正死因：七处伤口，每一处对应一条债务链。凶手不是一个人——是一个组织。报告最后一页画着一个标记：地府财政司的印章。下面一行字：沈万通查到了不该查到的东西。他查的不是账——是财政司内部的功德币洗钱链。'

gw = DeepSeekGateway(config)
prompts = PromptManager(config)
asm = StructuredAssembler(config)
prev_path = Path('output/chapters/第80章/正文.md')
recent = prev_path.read_text(encoding='utf-8')[-1500:] if prev_path.exists() else ''

print('=== 图谱注入 ===')
ctx = asyncio.run(asm.assemble(81, beat, chars, world, narrator_guide=VOICE, last_emotion='紧张'))
if ctx.graph_insights:
    print(ctx.graph_insights)
else:
    print('[FAIL] 图谱注入失败——无数据返回')
    exit(1)

print(f'\n=== 生成第81章 ===')
gen = Generator(config, gw, prompts)
result = asyncio.run(gen.generate_chapter(
    chapter_num=81, beat=beat, characters=chars, world=world,
    last_emotion='紧张', recent_chapters=recent, narrator_guide=VOICE,
    temperature=0.95, segmented=False, chapter_type='normal',
))
gen.save_chapter(result)
print(f'Ch81: {result.word_count}字')

m = json.loads(Path('output/chapters/第81章/meta.json').read_text(encoding='utf-8'))
m['key_characters'] = ['沈夜', '老白']
Path('output/chapters/第81章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
