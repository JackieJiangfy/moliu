import asyncio
from moliu.config import Config
from moliu.sync.client import MomaituSyncClient

config = Config()

new_chars = [
    {"name": "蒋副司长", "one_line_pitch": "地府财政司副司长，沈万通旧部，为夺渡劫基金不择手段", "role_type": "villain", "status": "active"},
    {"name": "秦馆长", "one_line_pitch": "市博物馆副馆长，沈万通借过铜镜还回来多了道裂纹", "role_type": "support", "status": "active"},
    {"name": "小顾", "one_line_pitch": "审计局新人，赵铁面派来帮沈夜熟悉黑市规则的年轻人", "role_type": "support", "status": "active"},
    {"name": "周万贯", "one_line_pitch": "当铺老板老鬼，用功德碑碎片换了孙子看一眼铜镜", "role_type": "minor", "status": "active"},
    {"name": "白七爷", "one_line_pitch": "千年厉鬼，等了三千七百年等女儿一句我那天没偷东西", "role_type": "support", "status": "active"},
    {"name": "周建国", "one_line_pitch": "跳楼老板，被沈夜审计出把公司钱转给了小三", "role_type": "minor", "status": "active"},
    {"name": "刘处", "one_line_pitch": "地府财政司处长，拿本票来查封银行被沈夜用票据法怼回去", "role_type": "minor", "status": "active"},
    {"name": "赵铁面", "one_line_pitch": "地府审计局局长，沈万通的暗处合伙人，共管渡劫基金", "role_type": "support", "status": "active"},
    {"name": "周正邦", "one_line_pitch": "地府财政司退休司长，唯一给沈万通签过合格的审计官", "role_type": "support", "status": "active"},
    {"name": "顾三娘", "one_line_pitch": "被丈夫卖掉的女子，沈万通帮她是因为她长得像沈夜的妈", "role_type": "minor", "status": "dead"},
    {"name": "陈老四", "one_line_pitch": "木匠，投胎四次守着没盖完的房子", "role_type": "minor", "status": "active"},
    {"name": "白露", "one_line_pitch": "白七爷之女，被体育老师害死，死前最后一句是跟我爸说我那天没偷东西", "role_type": "support", "status": "dead"},
    {"name": "张建国", "one_line_pitch": "白露学校的体育老师，三年前猥亵学生被开除，白露案凶手", "role_type": "villain", "status": "dead"},
    {"name": "陈小满", "one_line_pitch": "八岁小鬼，攒了三年功德币给妈妈续命，亡灵银行第一个客户", "role_type": "support", "status": "active"},
]


async def main():
    client = MomaituSyncClient(base_url=config.momaitu_base_url, username=config.momaitu_username, password=config.momaitu_password)
    ok, fail = 0, 0
    for c in new_chars:
        try:
            await client.sync_character(config.momaitu_novel_id, {
                "name": c["name"],
                "one_line_pitch": c["one_line_pitch"],
                "role_type": c["role_type"],
                "status": c["status"],
            })
            ok += 1
        except Exception as e:
            fail += 1
            print(f'{c["name"]}: FAIL')
    print(f'{ok} OK, {fail} FAIL')


asyncio.run(main())
