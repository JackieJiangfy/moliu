"""Focused audit of Ch91-125"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

chapters = []
for ch_num in range(91, 126):
    d = Path(f'output/chapters/第{ch_num}章')
    tf = d / '正文.md'
    mf = d / 'meta.json'
    if tf.exists():
        text = tf.read_text('utf-8')
        meta = json.loads(mf.read_text('utf-8')) if mf.exists() else {}
        chapters.append((ch_num, meta, text))

print(f'Ch91-125: {len(chapters)} 章\n')

# ===== 1. Check for ALL AI artifacts =====
print('='*50)
print('1. AI 残渣/异常开头')
print('='*50)
found = 0
for ch_num, meta, text in chapters:
    first = text.strip().split('\n')[0].strip()
    lines = text.strip().split('\n')
    if first.startswith('## 第'):
        print(f'  ❌ Ch{ch_num}: Markdown标题 "{first[:60]}"')
        found += 1
    if first.startswith('<') and first.endswith('>'):
        print(f'  ❌ Ch{ch_num}: 场景标记 "{first}"')
        found += 1
    if re.match(r'第[一二三四五六七八九十]+\s*章', first):
        print(f'  ❌ Ch{ch_num}: 章节残渣 "{first[:60]}"')
        found += 1
    # Check for empty/whitespace-only first lines
    if lines and lines[0].strip() == '' and len(lines) > 1 and lines[1].strip().startswith('<'):
        print(f'  ❌ Ch{ch_num}: 空行+场景标记')
        found += 1
if found == 0:
    print('  ✅ 无AI残渣')

# ===== 2. Check all transitions =====
print()
print('='*50)
print('2. 每章衔接 (末→首)')
print('='*50)
issues = 0
for i in range(len(chapters)-1):
    ch_c, _, text_c = chapters[i]
    ch_n, _, text_n = chapters[i+1]
    lc = [l.strip() for l in text_c.split('\n') if l.strip()]
    ln = [l.strip() for l in text_n.split('\n') if l.strip()]
    if not lc or not ln:
        continue
    last, first = lc[-1][:130], ln[0][:130]

    # Check if this is a known-fixed pair
    if ch_c in [108,109,110,118,119]:
        # We already reviewed these
        pass

    # Check for time jump coherence
    time_gap = False
    for tw in ['第二天','次日','三天后','一周后','一个月后','早上','晚上','凌晨']:
        if first.startswith(tw) or tw in first[:20]:
            time_gap = True
            break

    # Always print for this range (climax)
    print(f'  Ch{ch_c}→Ch{ch_n}:')
    print(f'    末: {last}')
    print(f'    首: {first}')
    if time_gap:
        print(f'    ↳ 时间跳跃')
    print()

# ===== 3. Plot resolution check =====
print('='*50)
print('3. 情节线收束')
print('='*50)
threads = {
    '曹桂兰|许薇|陈念': [], '顾长明': [], '钟国良': [], '蒋继先|蒋副司长': [],
    '韩济川': [], '042': [], '003': [], '验钞机': [],
    '赵铁面': [], '赵兰': [],
}
for ch_num, meta, text in chapters:
    for key in threads:
        if re.search(key, text):
            threads[key].append(ch_num)
for key, chs in sorted(threads.items(), key=lambda x: min(x[1]) if x[1] else 999):
    if chs:
        gap_warn = ''
        for i in range(1, len(chs)):
            if chs[i] - chs[i-1] > 15:
                gap_warn = f' ⚠️ 大缺口Ch{chs[i-1]}→Ch{chs[i]}'
        print(f'  {key}: Ch{min(chs)}-Ch{max(chs)}, {len(chs)}章{gap_warn}')

# ===== 4. Character arcs complete? =====
print()
print('='*50)
print('4. 角色终局状态')
print('='*50)
for name in ['沈夜','老白','沈万通','顾长明','钟国良','蒋继先','赵兰','许薇','赵铁面','韩济川']:
    last_ch = 0
    for ch_num, meta, text in chapters:
        if name in text:
            last_ch = ch_num
    status = '✅ 收束' if last_ch >= 120 else f'⚠️ 停在Ch{last_ch}'
    if last_ch == 0:
        status = '❌ 未出现'
    print(f'  {name}: {status}')

# ===== 5. Specific contradiction check =====
print()
print('='*50)
print('5. 前后矛盾检查')
print('='*50)

# 沈万通: dead or alive?
swt_dead = []
swt_alive_hint = []
for ch_num, meta, text in chapters:
    if '沈万通' not in text: continue
    if re.search(r'沈万通.*死|沈万通.*坟|沈万通.*埋|沈万通.*遗|沈万通.*没了', text):
        swt_dead.append(ch_num)
    if re.search(r'沈万通.*活着|沈万通没死|你爹还在|他没死', text):
        swt_alive_hint.append(ch_num)
if swt_alive_hint:
    print(f'  ⚠️ 沈万通暗示存活: Ch{min(swt_alive_hint)}-Ch{max(swt_alive_hint)}')
else:
    print(f'  ✅ 沈万通已死，无矛盾')

# 八十七亿 consistency
for ch_num, meta, text in chapters:
    amounts = re.findall(r'(\d+)[亿万千]', text)
    if '87亿' in text or '八十七亿' in text:
        pass  # core plot point

# Check if any character's motivation contradicts
contradictions = []
for ch_num, meta, text in chapters:
    if '韩济川活着' in text or '韩济川还在' in text:
        contradictions.append((ch_num, '韩济川存活'))
    if '蒋继先.*1987' in text:
        contradictions.append((ch_num, '年份矛盾'))
if contradictions:
    for ch, desc in contradictions:
        print(f'  ❌ Ch{ch}: {desc}')
else:
    print(f'  ✅ 无动机/状态矛盾')

# ===== 6. Word count anomalies =====
print()
print('='*50)
print('6. 字数异常')
print('='*50)
for ch_num, meta, text in chapters:
    wc = meta.get('word_count', 0)
    if wc < 1200: print(f'  ⚠️ Ch{ch_num}: {wc}字 (偏短)')
    elif wc > 4000: print(f'  ⚠️ Ch{ch_num}: {wc}字 (偏长)')

print()
print('完毕')
