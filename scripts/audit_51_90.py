"""Focused audit of Ch51-90"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

chapters = []
for ch_num in range(51, 91):
    d = Path(f'output/chapters/第{ch_num}章')
    tf = d / '正文.md'
    mf = d / 'meta.json'
    if tf.exists():
        text = tf.read_text('utf-8')
        meta = json.loads(mf.read_text('utf-8')) if mf.exists() else {}
        chapters.append((ch_num, meta, text))

print(f'Ch51-90: {len(chapters)} 章\n')

# ===== 1. All transitions =====
print('='*50)
print('1. 章间衔接')
print('='*50)
skips = 0
for i in range(len(chapters)-1):
    ch_c, _, text_c = chapters[i]
    ch_n, _, text_n = chapters[i+1]
    lc = [l.strip() for l in text_c.split('\n') if l.strip()]
    ln = [l.strip() for l in text_n.split('\n') if l.strip()]
    if not lc or not ln:
        continue
    last, first = lc[-1][:120], ln[0][:120]

    # Detect actual scene jumps (different location, no transition word)
    loc_words = ['银行','办公室','财政','审计','巷子','茶楼','墓园','码头','阴市','档案','临江','超市','柳河路']
    loc_c = [w for w in loc_words if w in last]
    loc_n = [w for w in loc_words if w in first]
    transition_words = ['第二天','次日','三天后','早上','晚上','凌晨','之后','回到','返回']
    has_transition = any(tw in first for tw in transition_words)

    if loc_c and loc_n and set(loc_c) != set(loc_n) and not has_transition:
        skips += 1
        if skips <= 8:
            print(f'  ⚠️ Ch{ch_c}→Ch{ch_n}: {loc_c}→{loc_n}')
            print(f'     末: {last}')
            print(f'     首: {first}')
            print()

# ===== 2. Plot arcs =====
print('='*50)
print('2. 情节线追踪')
print('='*50)
plots = {
    '蒋副司长.*查封': [], '本票.*兑付': [], '渡劫基金': [],
    '铜章': [], '功德碑': [], '顾三娘': [], '顾长明': [],
    '母版碎片': [], '白七爷': [], '周万贯': [], '秦馆长': [],
}
for ch_num, meta, text in chapters:
    for key in plots:
        if re.search(key, text):
            plots[key].append(ch_num)
for key, chs in sorted(plots.items(), key=lambda x: min(x[1]) if x[1] else 0):
    if chs:
        print(f'  {key}: Ch{min(chs)}-Ch{max(chs)}, {len(chs)}章')
        # Check for gaps > 5 chapters within the arc
        for i in range(1, len(chs)):
            if chs[i] - chs[i-1] > 8:
                print(f'    ⚠️ 缺口: Ch{chs[i-1]}→Ch{chs[i]} ({chs[i]-chs[i-1]}章)')

# ===== 3. Character tracking =====
print()
print('='*50)
print('3. 主要角色出场连续性 (Ch51-90)')
print('='*50)
main = ['沈夜','老白','赵铁面','孟小鱼','蒋副司长','顾三娘','顾长明','白七爷','周万贯','秦馆长','刘处']
for name in main:
    chs = []
    for ch_num, meta, text in chapters:
        if name in text:
            chs.append(ch_num)
    if not chs:
        print(f'  {name}: ❌ 未出现')
    else:
        gaps = []
        for i in range(1, len(chs)):
            if chs[i] - chs[i-1] > 5:
                gaps.append(f'Ch{chs[i-1]}→Ch{chs[i]}({chs[i]-chs[i-1]}章)')
        gap_str = f' ⚠️ {", ".join(gaps)}' if gaps else ''
        print(f'  {name}: Ch{min(chs)}-Ch{max(chs)}, {len(chs)}章{gap_str}')

# ===== 4. AI artifacts =====
print()
print('='*50)
print('4. AI 残渣/标题')
print('='*50)
for ch_num, meta, text in chapters:
    first = text.strip().split('\n')[0].strip()
    if first.startswith('## 第') or first.startswith('<') or re.match(r'第[一二三]章', first):
        print(f'  ❌ Ch{ch_num}: {first[:60]}')

# ===== 5. Anomalies =====
print()
print('='*50)
print('5. 字数异常 / 内容特征')
print('='*50)
for ch_num, meta, text in chapters:
    wc = meta.get('word_count', 0)
    if wc < 1200: print(f'  Ch{ch_num}: {wc}字 ⚠️偏短')
    elif wc > 3500: print(f'  Ch{ch_num}: {wc}字 ⚠️偏长')
    if '卷终' in text: print(f'  Ch{ch_num}: 含"卷终"')

# ===== 6. Check key number consistency =====
print()
print('='*50)
print('6. 关键数字一致性')
print('='*50)
for ch_num, meta, text in chapters:
    for pat in ['三千万', '1400万', '一千八百万', '三千七百年', '047号', '042号', '002号']:
        if pat in text:
            pass  # just tracking existence
    # Check 顾长明 first mention timing
    if '顾长明' in text and ch_num < 82:
        for i, line in enumerate(text.split('\n')):
            if '顾长明' in line:
                if ch_num not in [c for c,_,_ in chapters if '顾长明' in text]:
                    pass
                break

print()
# Check number of chapters mentioning 曹桂兰 before Ch86 (should be 0 since she's introduced in Ch86)
cao_early = []
for ch_num, meta, text in chapters:
    if '曹桂兰' in text:
        cao_early.append(ch_num)
print(f'  曹桂兰首次出现: Ch{min(cao_early) if cao_early else "未出现"}')
print(f'  曹桂兰区间: Ch{min(cao_early)}-Ch{max(cao_early)} ({len(cao_early)}章)' if cao_early else '  曹桂兰: 未出现')

print()
print('完毕')
