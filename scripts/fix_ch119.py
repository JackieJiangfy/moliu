"""Regenerate Ch119 - cemetery visit after 蒋继先 surrender"""
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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。情感收敛不煽情，结尾有重量。'

beat = ('沈夜从财政司出来已经是深夜。他给赵铁面打了个电话——赵铁面说你在哪，'
        '沈夜说刚从蒋继先办公室出来，他答应自首了。赵铁面沉默了几秒说：你一个人搞定的？'
        '沈夜说不是我——是我爹的验钞机。然后他打车去了临江墓园，在第七块砖下面找到了042号箱。'
        '箱子里面是他爹沈万通的最终调查记录——韩济川洗钱链的完整证据，从1987年到2019年，'
        '每一笔账、每一个账户、每一个经手人，全部写得清清楚楚。最后一页是他爹写给沈夜的短信：'
        '小夜，这些账我查了半辈子。我没做完——但我相信你能做完。记住，做账不是为了翻旧账，'
        '是为了让以后的人不用再查同一笔账。沈夜在坟前蹲了很久。老白飘在旁边没说话。'
        '天亮之前他把箱子合上，站起来说：走。回去上班。')

gw = DeepSeekGateway(config)
prompts = PromptManager(config)
asm = StructuredAssembler(config)

prev_text = Path('output/chapters/第118章/正文.md').read_text(encoding='utf-8')
recent = prev_text[-1500:]

print('Ch119 graph:', end=' ')
ctx = asyncio.run(asm.assemble(119, beat, chars, world, narrator_guide=VOICE, last_emotion='感动'))
print(f'{len(ctx.graph_insights)}c' if ctx.graph_insights else 'FAIL')

gen = Generator(config, gw, prompts)
result = asyncio.run(gen.generate_chapter(
    chapter_num=119, beat=beat, characters=chars, world=world,
    last_emotion='感动', recent_chapters=recent, narrator_guide=VOICE,
    temperature=0.95, segmented=False,
    chapter_type='climax',
))
gen.save_chapter(result)
print(f'  -> {result.word_count}w')

# Check for headers
text = Path('output/chapters/第119章/正文.md').read_text('utf-8')
if text.startswith('## 第') or (text.strip() and text.strip()[0] == '<'):
    # Clean up bad opening
    lines = text.split('\n')
    if lines[0].startswith('<') or lines[0].startswith('## 第'):
        print(f'  Cleaning bad header: {lines[0][:80]}')
    clean_lines = [l for l in lines if not (l.startswith('<') and l.endswith('>') and len(l) < 50)]
    clean_lines = [l for l in clean_lines if not l.startswith('## 第')]
    if clean_lines != lines:
        # Only remove the first bad line/scene marker
        bad_first = lines[0].strip()
        if bad_first.startswith('<') and bad_first.endswith('>'):
            text = '\n'.join(lines[1:]).lstrip()
            Path('output/chapters/第119章/正文.md').write_text(text, encoding='utf-8')
            print(f'  Removed scene marker: {bad_first}')

# Final check
text = Path('output/chapters/第119章/正文.md').read_text('utf-8')
wc = len(re.findall(r'[一-鿿㐀-䶿]', text))
print(f'  First line: {text[:100]}')
print(f'  Words: {wc}')

m = json.loads(Path('output/chapters/第119章/meta.json').read_text(encoding='utf-8'))
m['word_count'] = wc
m['key_characters'] = ['沈夜','老白','沈万通','赵铁面']
Path('output/chapters/第119章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
