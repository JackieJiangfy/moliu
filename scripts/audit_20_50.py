"""Focused audit of Ch20-50"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

chapters = []
for ch_num in range(20, 51):
    d = Path(f'output/chapters/第{ch_num}章')
    tf = d / '正文.md'
    mf = d / 'meta.json'
    if tf.exists():
        text = tf.read_text('utf-8')
        meta = json.loads(mf.read_text('utf-8')) if mf.exists() else {}
        chapters.append((ch_num, meta, text))

print(f'Ch20-50: {len(chapters)} 章\n')

# ===== 1. All transitions =====
print('='*50)
print('1. 每章衔接')
print('='*50)
for i in range(len(chapters)-1):
    ch_c, _, text_c = chapters[i]
    ch_n, _, text_n = chapters[i+1]
    lc = [l.strip() for l in text_c.split('\n') if l.strip()]
    ln = [l.strip() for l in text_n.split('\n') if l.strip()]
    if lc and ln:
        last = lc[-1][:100]
        first = ln[0][:100]
        # Quick sanity: check if chapter N+1 first line references chapter N's last topic
        print(f'Ch{ch_c}→Ch{ch_n}:')
        print(f'  末: {last}')
        print(f'  首: {first}')
        print()

# ===== 2. Foreshadow tracking =====
print('='*50)
print('2. 伏笔追踪')
print('='*50)
foreshadows = {
    '渡劫基金': [], '铜章': [], '验钞机.*百分比': [], '赵铁面.*合伙人': [],
    '沈万通.*坏账': [], '三千万': [], '002号': [], '铜镜': [],
}
for ch_num, meta, text in chapters:
    for key in foreshadows:
        if re.search(key, text):
            foreshadows[key].append(ch_num)
for key, chs in foreshadows.items():
    if chs:
        print(f'  {key}: Ch{min(chs)}-Ch{max(chs)} ({len(chs)}章)')

# ===== 3. Character introductions =====
print()
print('='*50)
print('3. 角色首次出场 (Ch20-50)')
print('='*50)
new_chars = {}
for ch_num, meta, text in chapters:
    for name in ['赵铁面', '周正邦', '蒋副司长', '小顾', '顾长明', '秦馆长', '刘处',
                 '顾三娘', '白七爷', '白露', '周万贯', '陈老四', '张建国', '周建国']:
        if name in text and name not in new_chars:
            new_chars[name] = ch_num
for name, ch in sorted(new_chars.items(), key=lambda x: x[1]):
    print(f'  {name}: Ch{ch}')

# ===== 4. Plot logic check =====
print()
print('='*50)
print('4. 情节逻辑检查')
print('='*50)

# Check 渡劫基金 logic
fund_chapters = []
for ch_num, meta, text in chapters:
    if '渡劫基金' in text:
        fund_chapters.append(ch_num)
if fund_chapters:
    print(f'  渡劫基金线: Ch{min(fund_chapters)}-Ch{max(fund_chapters)}')

# Check 本票 (promissory note) logic
for ch_num, meta, text in chapters:
    if '本票' in text and '一千八百万' in text:
        print(f'  1800万本票: Ch{ch_num}')

# Check 验钞机 % numbers consistency
pct_refs = []
for ch_num, meta, text in chapters:
    for m in re.finditer(r'(\d{1,3})%', text):
        pct = int(m.group(1))
        context = text[max(0,m.start()-20):m.end()+20].replace('\n',' ')
        pct_refs.append((ch_num, pct, context))
if pct_refs:
    print(f'  验钞机百分比引用:')
    for ch, pct, ctx in pct_refs:
        print(f'    Ch{ch}: {pct}% - ...{ctx}...')

# ===== 5. AI artifacts =====
print()
print('='*50)
print('5. AI 残渣/异常')
print('='*50)
for ch_num, meta, text in chapters:
    lines = text.strip().split('\n')
    first = lines[0].strip()
    if first.startswith('## 第') or first.startswith('<') or re.match(r'第[一二三]章', first):
        print(f'  ❌ Ch{ch_num}: {first[:60]}')
    # Check for very short lines that look like scene breaks
    weird_scene_breaks = [l for l in lines if re.match(r'^[·•\-—]{3,}$', l.strip())]
    if weird_scene_breaks:
        print(f'  ⚠️ Ch{ch_num}: {len(weird_scene_breaks)} 个场景分隔线')

# ===== 6. Word count =====
print()
print('='*50)
print('6. 字数分布')
print('='*50)
wcs = [(ch, m.get('word_count',0)) for ch, m, _ in chapters]
for ch, wc in wcs:
    flag = ''
    if wc < 1200: flag = ' ⚠️偏短'
    elif wc > 3500: flag = ' ⚠️偏长'
    if flag:
        print(f'  Ch{ch}: {wc}字{flag}')

print()
print('完毕')
