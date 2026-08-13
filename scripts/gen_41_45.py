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
VOICE = '沈夜嘴欠吊儿郎当。老白嘴碎心软。孟小鱼不耐烦但靠谱。悬念推进，每章结尾验钞机亮一次。'

beats = {
    41: '沈夜把沈万通的录音又听了一遍。录音里有一句话他当时没注意——“客户存款凭证存在第三备份区”。他问老白第三备份区在哪。老白想了很久说不知道——你爹从没提过。沈夜打开那台破电脑，搜索“第三备份区”。系统弹出一条提示：该区域已被加密。解密密钥由两名共管人共同持有。第一名共管人：沈万通。第二名：待激活。',
    42: '孟小鱼查了地府档案——第二名共管人是谁。系统显示：赵铁面。沈夜愣住了。老白也愣住了。沈夜说赵铁面不是跟他爹是死对头吗。孟小鱼说正相反——赵铁面是你爹最早的合伙人。亡灵银行创立时一共有两个法人。沈万通是明面上的，赵铁面是暗处的。后来分道扬镳——赵铁面选择留在地府体制内，沈万通选择独立。但他们签过一份共管协议——任何时候，只要两个人同时授权，第三备份区就能打开。',
    43: '沈夜去找赵铁面。赵铁面坐在审计局的办公室里，面前堆着一摞文件。沈夜把共管协议放在桌上。赵铁面看了一眼，表情没有任何变化。他说我知道你会来。从你第一天接手亡灵银行我就知道。沈夜说那你愿意授权吗。赵铁面说可以。但有一个条件——打开第三备份区之后，无论里面是什么，你都不能对外公开。沈夜问为什么。赵铁面说因为里面存的不止是存款凭证。还有你爹跟我签的一份协议——一份我们两个人都希望永远不见天日的协议。',
    44: '沈夜同意了。赵铁面取出他的那半密钥——是一把实体的铜钥匙，跟保险柜那把一模一样。两把钥匙同时插入验钞机底部的锁孔。验钞机屏幕闪了一下，弹出一个界面——没有用户界面，只有一行行纯文本。第三备份区。沈夜一条条往下翻。翻到最后一条的时候，他的手停了。那是一条没有标题的记录。内容只有一行字：沈万通名下所有资产已于十九年前全部转移至渡劫基金。转移操作人：赵铁面。',
    45: '赵铁面说渡劫基金是你爹跟我共同设的——不是骗人的项目，是真金白银的资产池。那个池子里的钱，属于亡灵银行的每一个客户。你爹把那些资产锁进去，是为了不让任何人动它——包括他自己。这是你爹给客户留的最后一条后路。沈夜问那现在这笔钱在哪。赵铁面说在你的验钞机里——从你接手第一天开始。那个48%的倒计时不是计时器。是资产解冻进度。当你处理完所有坏账——它就到100%。到那一天，渡劫基金自动解除锁定。所有客户的本金和利息，一次性兑付。',
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
        temperature=0.95, segmented=False, chapter_type='climax' if ch_num >= 44 else 'normal',
    ))
    gen.save_chapter(result)
    print(f'Ch{ch_num}: {result.word_count}w')
print('Done')
