import asyncio, httpx
from moliu.config import Config

config = Config()

# Missing relationships
missing = [
    ("沈夜", "老白", "合伙人", "positive", 7, "三百年老鬼，从讨薪到并肩"),
    ("沈夜", "周建国", "债主", "positive", 4, "帮周建国核销坏账，条件是向老婆坦白"),
    ("沈夜", "陈小满", "恩人", "positive", 7, "帮八岁小鬼贷款给妈妈续命"),
    ("蒋副司长", "刘处", "上下级", "positive", 3, "刘处是蒋的下属"),
    ("沈夜", "刘处", "对手", "negative", 3, "刘处拿本票来查封被沈夜怼回去"),
    ("白七爷", "沈夜", "受恩", "positive", 6, "沈夜帮白七爷查明女儿死因"),
]


async def main():
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{config.momaitu_base_url}/auth/login", json={"username": config.momaitu_username, "password": config.momaitu_password})
        token = r.json()["data"]["token"]
        r = await c.get(f"{config.momaitu_base_url}/novel/{config.momaitu_novel_id}/characters", headers={"Authorization": token}, params={"page": 1, "size": 50})
        ids = {ch["name"]: ch["id"] for ch in r.json()["data"]["records"]}

    for src, tgt, rtype, cat, intensity, desc in missing:
        sid = ids.get(src)
        tid = ids.get(tgt)
        if sid and tid:
            try:
                await c.post(
                    f"{config.momaitu_base_url}/novel/{config.momaitu_novel_id}/relationships",
                    json={"source_id": sid, "target_id": tid, "rel_type": rtype, "category": cat, "directed": True, "intensity": intensity, "description": desc},
                    headers={"Authorization": token},
                )
                print(f"  {src} -> {tgt}: OK")
            except Exception as e:
                print(f"  {src} -> {tgt}: FAIL")
        else:
            print(f"  {src}({sid}) -> {tgt}({tid}): NOT FOUND")


asyncio.run(main())
