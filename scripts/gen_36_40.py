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
    36: '财政部的人叫刘处。他看着本票脸色发青——一千八百万，兑付方是财政部驻阳间办事处。刘处说这张本票是废票——签发日期是十九年前，早过了兑付期。沈夜说我查过地府票据法——本票的诉讼时效是三千年。这张票还有两千九百八十一年。刘处沉默了。他收起冻结令转身走了——但临走时说了一句话：你爹当年也是拿这张本票跟我谈的。他没谈赢。你也一样。',
    37: '刘处走后沈夜把本票锁进保险柜。老白问他为什么不直接兑付。沈夜说兑了就没了——留着它当筹码，比兑了值钱。孟小鱼带来消息：财政部内部因为这张本票已经吵翻了——赵铁面一系想压下，周正邦那一系想公开。沈夜问周正邦跟赵铁面是什么关系。孟小鱼说他们曾经是合伙人——沈万通的事情让他们彻底决裂。',
    38: '陈小满母亲的续命贷款即将到期。沈夜在续约文件上签字的时候发现一个异常——系统显示陈小满母亲的寿命账户有一笔匿名存款，金额正好是一千八百万功德币。存款日期是十九年前。沈夜把老白叫过来。老白看了很久说这笔钱不是你爹存的——他十九年前根本没这么多钱。那这笔钱是谁存的。验钞机忽然亮了一行字：存款人已注销。账户状态待解冻。',
    39: '沈夜找到周正邦查那笔匿名存款的源头。周正邦调出原始记录——存款人的账户编号是沈万通的。但不是他个人的账户——是亡灵银行法人账户的隐藏子账户。这个子账户从未被审计过，从未出现在任何账目中。沈夜盯着屏幕看了很久。老白在旁边说这意味着你爹一直在瞒着地府存一笔钱——存了十九年。为了什么。',
    40: '倒计时归零后第七天。验钞机再次亮起——这次不是新业务，是一段自动播放的录音。他爹的声音。录于十九年前。沈万通说小夜如果你听到这段话说明你已经接手了。那个子账户是我替你存的——不是钱，是三百一十二万客户的原始存款凭证。我跑之前把它们全部单独备份了一份。这样就算银行的账被地府封了，客户的钱还在。沈夜听完把录音关了。然后对老白说：开工。第二卷从这里开始。',
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
