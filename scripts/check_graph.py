import asyncio, httpx, json, sys
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = 'a7428d7d-fab5-48a1-b32c-4cccfd155a8a'
BASE = 'http://localhost:8080/api'
NOVEL_ID = 'b1c25acc6ed344bdea84aad861ca4f2f'

async def main():
    async with httpx.AsyncClient() as h:
        headers = {'Authorization': TOKEN}

        # Characters
        r = await h.get(f'{BASE}/novel/{NOVEL_ID}/characters', headers=headers)
        data = r.json().get('data', {})
        chars = data.get('records', []) if isinstance(data, dict) else []
        print(f'=== 角色 ({len(chars)}个) ===')
        name_to_id = {}
        for c in chars:
            cid = c.get('id','?')
            name = c.get('name','?')
            role = c.get('roleType','?')
            status = c.get('status','?')
            pitch = c.get('oneLinePitch','')
            print(f'  [{cid}] {name} ({role}, {status}) - {pitch}')
            name_to_id[name] = cid

        print()

        # Relationships
        r = await h.get(f'{BASE}/novel/{NOVEL_ID}/relationships', headers=headers)
        data = r.json().get('data', {})
        rels = data.get('records', []) if isinstance(data, dict) else []
        print(f'=== 已有关系 ({len(rels)}条) ===')
        for rel in rels:
            src = rel.get('sourceName','?')
            tgt = rel.get('targetName','?')
            rtype = rel.get('relType','?')
            print(f'  {src} -> {tgt}: {rtype}')

        print()
        print(f'角色名列表: {list(name_to_id.keys())}')

asyncio.run(main())
