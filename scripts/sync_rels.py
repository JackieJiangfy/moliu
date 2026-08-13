import asyncio, httpx, json
from moliu.config import Config

config = Config()

relations = [
    ("沈夜", "蒋副司长", "对手", "negative", 7, "渡劫基金争夺"),
    ("沈夜", "赵铁面", "共管人", "positive", 6, "共同持有渡劫基金密钥"),
    ("沈夜", "周正邦", "引路人", "positive", 5, "退休司长帮沈夜解密沈万通档案"),
    ("沈夜", "白七爷", "恩人", "positive", 6, "帮白七爷查明女儿死因"),
    ("沈夜", "陈小满", "恩人", "positive", 7, "帮陈小满贷款给妈妈续命"),
    ("沈夜", "周万贯", "交易", "positive", 4, "用铜镜换功德碑碎片"),
    ("沈夜", "秦馆长", "交易", "positive", 3, "用铜印换看铜镜一眼"),
    ("沈万通", "蒋副司长", "旧主", "positive", 7, "蒋曾是沈万通手下审计员"),
    ("沈万通", "赵铁面", "合伙人", "positive", 8, "共同创立亡灵银行和渡劫基金"),
    ("沈万通", "周正邦", "被审计者", "positive", 5, "唯一签过合格的审计官"),
    ("沈万通", "顾三娘", "恩人", "positive", 5, "出钱救她，因为她长得像沈夜的妈"),
    ("沈万通", "秦馆长", "欠债人", "negative", 3, "借铜镜还回来多了道裂纹"),
    ("白七爷", "白露", "父女", "positive", 9, "三千七百年等待女儿一句清白"),
    ("白露", "张建国", "受害者", "negative", 9, "被体育老师害死"),
    ("赵铁面", "小顾", "上下级", "positive", 4, "派小顾帮沈夜"),
    ("蒋副司长", "刘处", "上下级", "positive", 4, "刘处是蒋的下属"),
]


async def main():
    async with httpx.AsyncClient() as c:
        r = await c.post(f'{config.momaitu_base_url}/auth/login', json={"username": config.momaitu_username, "password": config.momaitu_password})
        token = r.json()["data"]["token"]
        r = await c.get(f'{config.momaitu_base_url}/novel/{config.momaitu_novel_id}/characters', headers={"Authorization": token}, params={"page": 1, "size": 50})
        ids = {ch["name"]: ch["id"] for ch in r.json()["data"]["records"]}

    ok, fail, skip = 0, 0, 0
    for src, tgt, rtype, cat, intensity, desc in relations:
        sid = ids.get(src)
        tid = ids.get(tgt)
        if not sid or not tid:
            skip += 1
            continue
        try:
            await c.post(
                f'{config.momaitu_base_url}/novel/{config.momaitu_novel_id}/relationships',
                json={"source_id": sid, "target_id": tid, "rel_type": rtype, "category": cat, "directed": True, "intensity": intensity, "description": desc},
                headers={"Authorization": token},
            )
            ok += 1
        except Exception:
            fail += 1

    print(f'{ok} OK, {fail} FAIL, {skip} SKIP')


asyncio.run(main())
