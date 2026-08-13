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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。悬念推进。每章结尾验钞机亮一次。'

beats = {
    71: '蒋副司长兑现了赵铁面的警告——财政司正式下发吊销亡灵银行法人资格的通知。沈夜必须在24小时内证明银行正常经营，否则查封。赵铁面打电话来说你只有一条路——让渡劫基金解冻到70%以上。沈夜问怎么做到。赵铁面说剩下16块碎片里有一块在我手里。沈夜说你为什么不早说。赵铁面说因为这块碎片是你爹留给我的——不是给你的。留给我的条件是当你走投无路的时候才拿出来。',
    72: '赵铁面的碎片上刻着一个名字——沈万通本人。这块碎片是所有碎片的母版——有了它，其他碎片会自动加速回收。沈夜把母版碎片贴在验钞机上。屏幕上的数字从68%开始跳动——不是一次性跳，是一点一点往上爬。老白在旁边盯着屏幕，算盘珠子拨得比心跳还快。数字停在75%的时候，沈夜说够了。赵铁面说不够——蒋要的不是70%，是让你主动放弃法人资格。他真正的目标不是银行——是渡劫基金的控制权。',
    73: '沈夜直接去财政司找蒋副司长。他把母版碎片放在蒋的桌上说你要渡劫基金的控制权——可以。但我有一个条件。让我把坏账处理完。剩下的25%，每一笔我亲自处理——你在旁边看着。我处理完那天，渡劫基金自动解冻，控制权转给谁我不在乎——只要客户的钱能到账。蒋看着他：你觉得我会信。沈夜说你不信——但你不会错过站在旁边看我还完最后一笔债的机会。你等这一天等了十九年。',
    74: '蒋同意了。条件是他派一个监督员全程跟着沈夜。监督员不是别人——是小顾。沈夜说你到底是赵铁面的人还是蒋的人。小顾说我是审计局的人——我只认账。沈夜带着小顾开始处理剩下的坏账。每核销一笔，验钞机数字跳一个点。小顾在旁边记账，一笔一笔，工整得像印刷的。处理到第十笔的时候小顾说沈法人你知道你跟你爹最大的区别是什么吗——你爹处理坏账的时候从来不让人看。你是一笔一笔摊开的。',
    75: '两周后，坏账清零。验钞机屏幕上的数字停在100%。沈夜把所有文件整理好，叫来赵铁面、蒋副司长、周正邦、孟小鱼——所有人站在银行柜台前面。他把两台验钞机并排摆好，按下确认键。屏幕亮起一行字：渡劫基金解冻。312万客户存款凭证全部兑付。蒋看着那行字很久。然后说了一句话：你爹输了一辈子。你赢了。沈夜说我爹没输。他只是跑得太早——不知道会有人替他收。',
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
        chapter_type='climax' if ch_num >= 74 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'Ch{ch_num}: {result.word_count}w')

# Sync to graph
print('Syncing to graph...')
import json
for i in range(71, 76):
    mp = Path(f'output/chapters/第{i}章/meta.json')
    if mp.exists():
        m = json.loads(mp.read_text(encoding='utf-8'))
        m['key_characters'] = ['沈夜', '老白']
        if i in (71, 73, 75): m['key_characters'].append('蒋副司长')
        if i in (71, 72): m['key_characters'].append('赵铁面')
        if i == 74: m['key_characters'].append('小顾')
        if i == 75: m['key_characters'].extend(['孟小鱼', '周正邦'])
        mp.write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')

print('Done! 71-75 generated + meta updated.')
