"""Fix 墨脉图 relationships - v2 with correct IDs"""
import asyncio, httpx
from moliu.config import Config

config = Config()
BASE = config.momaitu_base_url
NOVEL_ID = config.momaitu_novel_id

async def main():
    async with httpx.AsyncClient() as http:
        r = await http.post(f'{BASE}/auth/login', json={
            'username': config.momaitu_username,
            'password': config.momaitu_password
        })
        token = r.json()['data']['token']
        headers = {'Authorization': token}

        # Fetch all characters with large page size
        r = await http.get(f'{BASE}/novel/{NOVEL_ID}/characters?size=50', headers=headers)
        chars = r.json()['data']['records']
        name_to_id = {c['name']: c['id'] for c in chars}
        print(f'Characters: {len(name_to_id)}')

        # Fetch existing relationships
        r = await http.get(f'{BASE}/novel/{NOVEL_ID}/relationships?size=100', headers=headers)
        existing = r.json()['data']['records']
        existing_pairs = set()
        for rel in existing:
            existing_pairs.add((rel.get('sourceName',''), rel.get('targetName',''), rel.get('relType','')))
        print(f'Existing relationships: {len(existing)}')

        # Build all needed relationships
        rels_to_add = [
            # Core family
            ('沈夜', '沈万通', '父子', 'positive', 10, '沈夜是沈万通的儿子，继承亡灵银行'),
            ('沈夜', '赵兰', '母子', 'positive', 8, '沈夜与母亲赵兰，因父亲跑路疏远多年后和解'),
            ('沈万通', '赵兰', '夫妻', 'positive', 7, '沈万通与赵兰，为保护妻儿跑路十九年'),
            # 韩济川 family web
            ('韩济川', '蒋继先', '岳父女婿', 'positive', 5, '韩济川是蒋继先的岳父'),
            ('韩济川', '顾长明', '岳父女婿', 'positive', 5, '韩济川是顾长明的岳父'),
            ('顾长明', '蒋继先', '连襟', 'positive', 5, '顾长明与蒋继先是连襟，共同包庇洗钱链'),
            # 沈夜 vs antagonists
            ('沈夜', '顾长明', '对峙', 'negative', 7, '沈夜追查顾长明包庇十九年的洗钱链'),
            ('沈夜', '钟国良', '追查', 'negative', 8, '沈夜追查钟国良管理的暗账系统'),
            ('沈夜', '蒋继先', '追查', 'negative', 8, '沈夜追查蒋继先经手的暗账'),
            ('沈夜', '韩济川', '间接敌对', 'negative', 6, '沈夜间接对抗已故的韩济川遗留的洗钱链'),
            # 沈夜 vs allies
            ('沈夜', '孟小鱼', '朋友', 'positive', 6, '沈夜与孟小鱼是朋友，多次帮他查档案'),
            ('沈夜', '许薇', '恩人', 'positive', 6, '沈夜帮许薇恢复母亲曹桂兰的名誉'),
            # 沈万通 relationships
            ('沈万通', '顾长明', '旧识', 'negative', 7, '沈万通与顾长明旧识，顾长明对其见死不救'),
            ('沈万通', '钟国良', '被迫交易', 'negative', 8, '沈万通被迫与钟国良交易以保护儿子'),
            ('沈万通', '蒋继先', '被出卖', 'negative', 9, '沈万通被蒋继先出卖，最终配合作死'),
            ('沈万通', '韩济川', '死敌', 'negative', 10, '沈万通对抗韩济川的洗钱链，最终因此而死'),
            ('沈万通', '曹桂兰', '证人', 'positive', 7, '沈万通是曹桂兰举报信的共同见证人'),
            ('沈万通', '老白', '雇主', 'positive', 8, '沈万通是老白追随三百年的雇主'),
            # 老白
            ('老白', '钟国良', '旧识', 'negative', 5, '老白与钟国良三百年前在地府财务部共事'),
            # Villains
            ('钟国良', '蒋继先', '同谋', 'negative', 7, '钟国良与蒋继先共同运作暗账系统'),
            ('钟国良', '韩济川', '上下级', 'negative', 6, '钟国良是韩济川生前的副手'),
            # 曹桂兰
            ('曹桂兰', '许薇', '母女', 'positive', 9, '曹桂兰是许薇的亲生母亲，失踪前写举报信'),
            ('顾长明', '曹桂兰', '间接害死', 'negative', 7, '顾长明包庇洗钱链间接导致曹桂兰失踪死亡'),
            # 顾长明
            ('顾长明', '沈万通', '见死不救', 'negative', 8, '顾长明知沈万通有难却未施援手'),
            # 沈万通 & 老白 bi-directional
            ('老白', '沈万通', '忠诚下属', 'positive', 9, '老白对沈万通忠心耿耿三百年'),
        ]

        ok, fail, skip = 0, 0, 0
        for src_name, tgt_name, rtype, cat, intensity, desc in rels_to_add:
            # Skip if already exists
            if (src_name, tgt_name, rtype) in existing_pairs:
                skip += 1
                continue

            src_id = name_to_id.get(src_name)
            tgt_id = name_to_id.get(tgt_name)
            if not src_id or not tgt_id:
                print(f'  SKIP {src_name}->{tgt_name}: missing ID')
                fail += 1
                continue

            body = {
                'sourceId': src_id,
                'targetId': tgt_id,
                'relType': rtype,
                'category': cat,
                'directed': 1,
                'intensity': intensity,
                'description': desc,
            }
            r = await http.post(f'{BASE}/novel/{NOVEL_ID}/relationships', json=body, headers=headers)
            if r.status_code == 200:
                ok += 1
            else:
                fail += 1
                print(f'  FAIL {src_name}->{tgt_name}: {r.status_code}')

        print(f'Added: {ok}, Skipped (exists): {skip}, Failed: {fail}')

        # Final count
        r = await http.get(f'{BASE}/novel/{NOVEL_ID}/relationships?size=100', headers=headers)
        rels = r.json()['data']['records']
        print(f'\nTotal relationships: {len(rels)}')
        # Group by source
        by_src = {}
        for rel in rels:
            src = rel.get('sourceName','?')
            by_src.setdefault(src, []).append(f'{rel.get("targetName")}({rel.get("relType")})')
        for src, targets in sorted(by_src.items()):
            print(f'  {src} ({len(targets)}): {", ".join(targets)}')

asyncio.run(main())
