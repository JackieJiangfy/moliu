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
    82: '尸检报告上的七条债务链对应地府财政司七个不同的部门。沈夜把报告给赵铁面看——赵铁面认出了其中四个部门的负责人。都是蒋副司长的上级或同僚。沈夜问这些人还在财政司吗。赵铁面说四个退休了，两个调走了，一个还在——是蒋副司长的顶头上司，财政司司长顾长明。沈夜问这个顾长明是什么人。赵铁面说他批了你爹三百多份审计报告——每一份都写着驳回。你爹跟他打了十九年交道，从来没赢过。',
    83: '沈夜让孟小鱼查顾长明的档案。孟小鱼翻遍了地府档案库——顾长明的公开履历干净得像新打印的。但有一个漏洞：他的退休金账户显示过去二十年持续有大额功德币入账，来源不明。沈夜说这笔钱是不是功德币洗钱链的痕迹。孟小鱼说不能确定——但如果是，这个洗钱链的规模远超亡灵银行的三千万坏账。沈夜说那多大。孟小鱼估算了一下——大概三百亿。',
    84: '沈夜回到银行把数字写在黑板上。老白看了很久说三百亿——你爹当年查的如果是这个，他跑路不是为了躲三千万。他是怕把你卷进来。沈夜说他已经把我卷进来了——跑了十九年，最后不还是我站在这儿。老白说你打算怎么办。沈夜说去找顾长明。老白说他是财政司司长，你一个破产银行的法人怎么找他。沈夜说他欠我爹十九年的驳回——每一笔都应该有个理由。我去看那些理由。',
    85: '沈夜去财政司调取沈万通全部审计档案。档案管理员是个老太，戴老花镜，不说话只翻本子。她翻到最后一页说沈万通的档案在十九楼——但十九楼不对外开放。沈夜问为什么。老太说十九楼是金融犯罪调查科的档案室。你爹的审计记录被金融犯罪科调走了——调走日期是你爹跑路的前一天。沈夜说你认识我爹。老太摘下眼镜擦了擦说我给他开了十九年档案室的门。每次都是驳回——但他从来不看驳回理由。只看结论。沈夜说你帮帮我。老太看了他很久然后把一把钥匙放在桌上说十九楼。左边第三个柜子。别让顾长明知道。',
}

for ch_num, beat in beats.items():
    gw = DeepSeekGateway(config)
    prompts = PromptManager(config)
    asm = StructuredAssembler(config)
    prev_path = Path(f'output/chapters/第{ch_num - 1}章/正文.md')
    recent = prev_path.read_text(encoding='utf-8')[-1500:] if prev_path.exists() else ''
    print(f'Ch{ch_num} graph:', end=' ')
    ctx = asyncio.run(asm.assemble(ch_num, beat, chars, world, narrator_guide=VOICE, last_emotion='紧张'))
    if ctx.graph_insights:
        print(f'{len(ctx.graph_insights)}c insights')
    else:
        print('[FAIL] 图谱无数据')
        exit(1)
    gen = Generator(config, gw, prompts)
    result = asyncio.run(gen.generate_chapter(
        chapter_num=ch_num, beat=beat, characters=chars, world=world,
        last_emotion='紧张', recent_chapters=recent, narrator_guide=VOICE,
        temperature=0.95, segmented=False, chapter_type='normal',
    ))
    gen.save_chapter(result)
    print(f'  -> {result.word_count}w')
    m = json.loads(Path(f'output/chapters/第{ch_num}章/meta.json').read_text(encoding='utf-8'))
    m['key_characters'] = ['沈夜','老白']
    if ch_num in (82,85): m['key_characters'].append('赵铁面')
    if ch_num == 83: m['key_characters'].append('孟小鱼')
    Path(f'output/chapters/第{ch_num}章/meta.json').write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')

print('Done! 82-85 generated with graph injection.')
