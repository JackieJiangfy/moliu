"""Deep audit of Ch20-125 for logic/story issues"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

CHAPTERS_DIR = Path('output/chapters')

# Load all chapters 20-125
chapters = []
for d in sorted(CHAPTERS_DIR.glob('第*章'), key=lambda d: int(re.search(r'\d+', d.name).group())):
    ch_num = int(re.search(r'\d+', d.name).group())
    if ch_num < 20:
        continue
    tf = d / '正文.md'
    mf = d / 'meta.json'
    if tf.exists():
        text = tf.read_text('utf-8')
        meta = json.loads(mf.read_text('utf-8')) if mf.exists() else {}
        chapters.append((ch_num, meta, text, d.name))

print(f'Ch20-125: {len(chapters)} 章\n')

# ===== 1. Check for AI scene markers =====
print('='*50)
print('1. AI 场景标记 / 残渣检查')
print('='*50)
for ch_num, meta, text, dname in chapters:
    first_line = text.strip().split('\n')[0].strip()
    if first_line.startswith('<') and first_line.endswith('>'):
        print(f'  ❌ Ch{ch_num}: 场景标记 "{first_line}"')
    if re.search(r'第[一二三]章', first_line):
        print(f'  ❌ Ch{ch_num}: 章节残渣 "{first_line[:50]}"')
    if text.strip().startswith('## 第'):
        print(f'  ❌ Ch{ch_num}: Markdown标题')
    # Check for odd patterns
    if '第三章' in first_line:
        print(f'  ❌ Ch{ch_num}: 包含"第三章"')

# ===== 2. Check all chapter transitions =====
print()
print('='*50)
print('2. 全部章节衔接 (Ch20→Ch125)')
print('='*50)
issues = 0
for i in range(len(chapters)-1):
    ch_curr, _, text_curr, _ = chapters[i]
    ch_next, _, text_next, _ = chapters[i+1]

    lines_c = [l.strip() for l in text_curr.split('\n') if l.strip()]
    lines_n = [l.strip() for l in text_next.split('\n') if l.strip()]
    if not lines_c or not lines_n:
        continue

    last = lines_c[-1]
    first = lines_n[0]

    # Check for time jumps with no transition
    time_jump_c = any(w in last for w in ['明天','第二天','三天后','晚上','早上','凌晨'])
    time_jump_n = any(w in first for w in ['第二天','三天后','一周后','一个月后'])

    # Check for location jumps without explanation
    locs_c = set(re.findall(r'(墓园|银行|办公室|超市|柳河路|财政司|临江|城中村|巷子|茶楼|面馆|审计局|财务部)', last))
    locs_n = set(re.findall(r'(墓园|银行|办公室|超市|柳河路|财政司|临江|城中村|巷子|茶楼|面馆|审计局|财务部)', first))

    # Flag if locations completely different and no time transition
    if locs_c and locs_n and not (locs_c & locs_n) and not time_jump_n:
        issues += 1
        if issues <= 10:
            print(f'  ⚠️ Ch{ch_curr}→Ch{ch_next}: 场景跳跃')
            print(f'     末({"/".join(locs_c)}): {last[:80]}')
            print(f'     首({"/".join(locs_n)}): {first[:80]}')

if issues == 0:
    print('  ✅ 衔接无异常')
else:
    print(f'  共 {issues} 处场景跳跃')

# ===== 3. Check numeric/logic consistency =====
print()
print('='*50)
print('3. 数字/逻辑一致性')
print('='*50)

# Check 八十七亿 consistency
for ch_num, meta, text, dname in chapters:
    if '八十七亿' in text or '87亿' in text:
        pass  # This is fine, core plot point

# Check if 韩济川 is dead or alive consistently
han_alive = []
han_dead = []
for ch_num, meta, text, dname in chapters:
    if '韩济川' not in text:
        continue
    if re.search(r'韩济川.*死|韩济川.*已故|韩济川.*遗嘱|死.*韩济川', text):
        han_dead.append(ch_num)
    if re.search(r'韩济川.*活着|韩济川还在|找韩济川|见韩济川', text):
        han_alive.append(ch_num)

if han_alive and han_dead:
    print(f'  ⚠️ 韩济川存活状态矛盾:')
    print(f'     明确已死: Ch{min(han_dead)}-Ch{max(han_dead)}')
    print(f'     暗示存活: Ch{min(han_alive)}-Ch{max(han_alive)}')
else:
    print(f'  ✅ 韩济川状态一致 (已故)')

# ===== 4. Check 验钞机 abilities consistency =====
print()
print('='*50)
print('4. 验钞机功能一致性')
print('='*50)
abilities = {}
for ch_num, meta, text, dname in chapters:
    if '验钞机' not in text:
        continue
    if '上传' in text or '云端' in text or '传输' in text:
        abilities.setdefault('云端上传', []).append(ch_num)
    if '暗账追踪' in text:
        abilities.setdefault('暗账追踪', []).append(ch_num)
    if '录音' in text or '记录' in text:
        abilities.setdefault('实时记录', []).append(ch_num)
    if '保险箱' in text and '验钞机' in text:
        if '激活' in text or '打开' in text or '扫了' in text:
            abilities.setdefault('开保险箱', []).append(ch_num)

for ab, chs in abilities.items():
    print(f'  {ab}: 首次Ch{min(chs)}, {len(chs)}章')

# ===== 5. Check unresolved plot threads =====
print()
print('='*50)
print('5. 未解决线索检查')
print('='*50)

# Check 042
for ch_num, meta, text, dname in chapters:
    if '042' in text:
        last_042 = ch_num
print(f'  042号箱: 最后出现 Ch{last_042}')

# Check 003
last_003 = 0
for ch_num, meta, text, dname in chapters:
    if '003' in text:
        last_003 = ch_num
print(f'  003号箱: 最后出现 Ch{last_003}' if last_003 else '  003号箱: 未出现')

# Check if 陈小满 mentioned after Ch58
for ch_num, meta, text, dname in chapters:
    if '陈小满' in text:
        last_cxm = ch_num
print(f'  陈小满: 最后出现 Ch{last_cxm}')

# Check if 白七爷 mentioned after Ch20
for ch_num, meta, text, dname in chapters:
    if '白七爷' in text:
        last_bai = ch_num
print(f'  白七爷: 最后出现 Ch{last_bai}')

# ===== 6. Check for contradictory character statements =====
print()
print('='*50)
print('6. 沈万通死亡时间一致性')
print('='*50)
death_refs = []
for ch_num, meta, text, dname in chapters:
    for m in re.finditer(r'(?:死了|跑了|失踪|跑路)(\d{1,3})年', text):
        death_refs.append((ch_num, m.group()))
    for m in re.finditer(r'(\d{1,3})年.*(?:跑路|失踪|死了)', text):
        death_refs.append((ch_num, m.group()))

for ch, ref in death_refs:
    print(f'  Ch{ch}: {ref}')

print()
print('='*50)
print('审查完毕')
print('='*50)
