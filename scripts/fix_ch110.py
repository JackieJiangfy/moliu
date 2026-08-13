"""Regenerate Ch110 to bridge Ch109→Ch111 continuity"""
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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。节奏紧凑，情感克制不煽情。'

# New beat: bridges Ch109 (柳河路之约) → Ch111 (墓园)
beat = ('沈夜带着老白去了柳河路88号旺旺超市。门口的冰柜嗡嗡响，一个老头坐在收银台后面看电视。'
        '沈夜说找钟国良。老头抬头看了他一眼，从柜台底下摸出一个牛皮纸信封递过来——钟国良上午来过了，'
        '留了这封信，说他等的人下午到。沈夜拆开信。钟国良的字写得很工整，像用尺子量过的。'
        '信上说：年轻人，我不能见你。你的通话被监听了——你爹当年的那台验钞机不只是记账用的，'
        '它同时也是个信号源。你激活暗账追踪的那一刻，蒋继先那边就收到了警报。我现在被他们的人盯着，'
        '露面等于害你。但你爹当年托我一件事——他说有朝一日他儿子来查账，让我把一句话原封不动地转告给他。'
        '那句话是：小夜，043不是我留给你的保险箱——是你出生那天我就给你买的保险。每个月二百功德币，'
        '攒了十九年。钟国良说我当年不懂他为什么要这样存钱。后来懂了——他不是在存钱。他是在用每个月二百块钱提醒自己，'
        '他还有个儿子在阳间活着。信的最后一行：去临江墓园。你的坟是空的。里面是你爹真正留给你的东西。'
        '沈夜把信折好放进口袋。老白问怎么了。沈夜说改道——先去墓园。')

gw = DeepSeekGateway(config)
prompts = PromptManager(config)
asm = StructuredAssembler(config)

# Use Ch109 text as recent context
prev_text = Path('output/chapters/第109章/正文.md').read_text(encoding='utf-8')
recent = prev_text[-1500:]

print('Ch110 graph:', end=' ')
ctx = asyncio.run(asm.assemble(110, beat, chars, world, narrator_guide=VOICE, last_emotion='紧张'))
print(f'{len(ctx.graph_insights)}c' if ctx.graph_insights else 'FAIL')

gen = Generator(config, gw, prompts)
result = asyncio.run(gen.generate_chapter(
    chapter_num=110, beat=beat, characters=chars, world=world,
    last_emotion='紧张', recent_chapters=recent, narrator_guide=VOICE,
    temperature=0.95, segmented=False,
    chapter_type='normal',
))
gen.save_chapter(result)
print(f'  -> {result.word_count}w')

# Update meta
m = json.loads(Path('output/chapters/第110章/meta.json').read_text(encoding='utf-8'))
m['key_characters'] = ['沈夜','老白','钟国良','沈万通']
Path('output/chapters/第110章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Ch110 regenerated!')
