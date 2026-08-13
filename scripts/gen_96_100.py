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

beats = {
    96: '沈夜把曹桂兰的举报信和沈万通的目击证词整理成一份完整的调查报告。他让赵铁面帮他约顾长明见面。赵铁面说你想好了——顾长明当了十九年财政司司长，地府的法律他比谁都熟。沈夜说我不是去告他。赵铁面问那你去干嘛。沈夜说去还他一份东西。他欠我爹十九年的驳回——现在我把报告放在他面前，让他自己决定是撕了还是认了。赵铁面沉默了。第二天他发来一条消息：明天下午三点，财政司顶楼会客室。顾长明愿意见你。',
    97: '沈夜独自上了财政司顶楼。顾长明坐在长桌尽头，六十多岁，穿一件深灰色的中山装，头发梳得一丝不苟。他面前的桌上什么都没有——没有文件，没有茶杯，没有任何东西可以让沈夜判断他的情绪。沈夜把报告放在桌上。顾长明没有翻——他只是看着沈夜说了一句话：你跟你父亲一样，喜欢把账记在纸上。沈夜说不一样——他记完就跑了。我记完会放在你面前。顾长明翻开了报告。他看了很久。然后摘下眼镜说：这笔洗钱链涉及财政司十二个部门，三任司长，总金额三百二十亿功德币。你想怎么办。沈夜说我把原始证据全部寄存在了一个你不能动的保险箱里。顾长明问哪个。沈夜说042。',
    98: '顾长明靠在椅背上。他沉默了很长时间——长到沈夜以为他睡着了。然后他开口：你父亲当年也坐在这把椅子前面，跟我说了一样的话。他说他查到了一条洗钱链，证据锁在042号保险箱里。他的条件是让我把所有驳回申请批掉——从此不再为难亡灵银行。沈夜问然后呢。顾长明说我问他如果我不批呢。你父亲说那就看谁先死。沈夜说我爹确实先死了。顾长明说不是我杀的。沈夜说我知道——你只是见死不救。顾长明没有说话。很久之后他说：042里的证据，你打算怎么用。',
    99: '沈夜说他不要顾长明下台，也不要三百亿洗钱链的数字——他要恢复曹桂兰的名誉。顾长明说她已经死了二十五年了。沈夜说她女儿还活着。那份举报信写在她失踪前一天——信上最后一句话是别让我的孩子以为她妈做错了事。顾长明看着沈夜很久。然后他从抽屉里拿出一份文件签了字：地府财政司关于恢复曹桂兰同志名誉的决定。他把文件推给沈夜说你父亲当年来找我的时候，如果开口是为曹桂兰，不是为亡灵银行，我会帮他的。沈夜收起文件。他说他不是不想帮曹桂兰——他是想先保住银行，再用银行帮她。只是他没活到那一天。',
    100: '沈夜把文件寄给了许薇。附了一张纸条：你妈的信我收到了。她的名誉恢复了。这笔账算清了。验钞机亮了一下——不是新业务，不是进度条，是一行他从没见过的字：001号保险箱状态更新——曹桂兰案，已结案。老白看着那行字说这机器在记的不是账。沈夜问那是什么。老白说它在记你爹没做完的事。你爹查了十九年，来不及查完。你查了几个月，替他查完了。沈夜靠在椅背上看着天花板。他说该查的查完了。剩下的就是一条——042。顾长明说里面的录像可以证明整个洗钱链的存在。那份录像，他还没看。',
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
        chapter_type='climax' if ch_num >= 97 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (96,97,98,99): m['key_characters'].append('顾长明')
    if ch_num in (97,98): m['key_characters'].append('赵铁面')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
print('Done!')
