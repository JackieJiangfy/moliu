"""Comprehensive audit of all 125 chapters"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from collections import Counter

CHAPTERS_DIR = Path('output/chapters')

def load_all():
    chapters = []
    for d in sorted(CHAPTERS_DIR.glob('第*章'), key=lambda d: int(re.search(r'\d+', d.name).group())):
        tf = d / '正文.md'
        mf = d / 'meta.json'
        if tf.exists():
            text = tf.read_text('utf-8')
            meta = json.loads(mf.read_text('utf-8')) if mf.exists() else {}
            chapters.append((meta.get('chapter_num',0), meta, text, d.name))
    return sorted(chapters, key=lambda c: c[0])

chapters = load_all()
print(f'共 {len(chapters)} 章\n')

# ===== 1. HEADER CHECK =====
print('='*50)
print('1. Markdown 标题检查')
print('='*50)
headers_found = []
for ch_num, meta, text, dname in chapters:
    m = re.match(r'^## 第[百零一二三四五六七八九十\d]+章', text)
    if m:
        headers_found.append((ch_num, m.group().strip()))
if headers_found:
    for ch, h in headers_found:
        print(f'  ❌ Ch{ch}: {h}')
else:
    print('  ✅ 无标题污染')

# ===== 2. CONTINUITY =====
print()
print('='*50)
print('2. 章节衔接检查（末句→首句）')
print('='*50)
breaks = 0
for i in range(len(chapters)-1):
    ch_curr, _, text_curr, _ = chapters[i]
    ch_next, _, text_next, _ = chapters[i+1]
    lines_c = [l.strip() for l in text_curr.split('\n') if l.strip()]
    lines_n = [l.strip() for l in text_next.split('\n') if l.strip()]
    if not lines_c or not lines_n:
        continue
    last = lines_c[-1]
    first = lines_n[0]

    # Heuristic: if both mention completely different locations/actions, flag it
    # Check for common continuity patterns
    is_good = False
    # Same location mention
    locs_c = set(re.findall(r'(墓园|银行|办公室|超市|柳河路|财政司|临江|城中村|巷子|茶楼|面馆)', last))
    locs_n = set(re.findall(r'(墓园|银行|办公室|超市|柳河路|财政司|临江|城中村|巷子|茶楼|面馆)', first))
    if locs_c & locs_n:
        is_good = True

    if not is_good and ch_curr >= 108 and ch_curr <= 111:
        # Already reviewed these
        continue

    # Show all for manual review (every 10th or suspicious)
    if ch_curr % 25 == 0 or ch_curr <= 3:
        print(f'  Ch{ch_curr}→Ch{ch_next}:')
        print(f'    末: {last[:100]}')
        print(f'    首: {first[:100]}')

# ===== 3. NAME CONSISTENCY =====
print()
print('='*50)
print('3. 人名一致性检查')
print('='*50)

# Check key names across all chapters
name_checks = {
    '许薇': [], '陈念': [], '陈秀莲': [],  # Should all be 许薇 now
    '曹桂兰': [],
    '钟国良': [],
    '蒋继先': [], '蒋副司长': [],
    '顾长明': [],
    '沈万通': [],
    '赵兰': [],
}
for ch_num, meta, text, dname in chapters:
    for name in name_checks:
        if name in text:
            name_checks[name].append(ch_num)

print('  许薇 (应为统一名):', f'Ch{min(name_checks["许薇"])}-Ch{max(name_checks["许薇"])}' if name_checks['许薇'] else '❌ 未出现')
print('  陈念 (曾用名):', f'Ch{min(name_checks["陈念"])}-Ch{max(name_checks["陈念"])}' if name_checks['陈念'] else '✅ 已统一')
print('  陈秀莲 (错误名):', f'出现{len(name_checks["陈秀莲"])}次' if name_checks['陈秀莲'] else '✅ 已统一')
print('  蒋继先:', f'{len(name_checks["蒋继先"])}章' if name_checks['蒋继先'] else '❌')
print('  蒋副司长(旧名):', f'出现{len(name_checks["蒋副司长"])}次' if name_checks['蒋副司长'] else '✅ 已统一')

# ===== 4. REPETITION CHECK =====
print()
print('='*50)
print('4. 高频重复句式检查')
print('='*50)
repetitions = {
    '验钞机亮了': 0,
    '老白飘在': 0,
    '算盘珠子': 0,
    '沉默了.*久': 0,
    '灯管.*闪': 0,
    '城中村.*炒菜': 0,
    '吊儿郎当': 0,
    '裂缝.*延伸到墙角': 0,
    '靠在椅背上': 0,
    '没接话': 0,
    '张了张嘴': 0,
    '眼眶.*红': 0,
    '搪瓷罐': 0,
}
for ch_num, meta, text, dname in chapters:
    for phrase in repetitions:
        count = len(re.findall(phrase, text))
        repetitions[phrase] += count

for phrase, count in sorted(repetitions.items(), key=lambda x: -x[1]):
    if count > 10:
        print(f'  ⚠️ "{phrase}" 出现 {count} 次（全125章）')

# ===== 5. TIMELINE CHECK =====
print()
print('='*50)
print('5. 时间线关键词分布')
print('='*50)
time_words = {
    '十九年': [], '三百年': [], '1987': [], '2004': [], '2019': [], '2021': [],
}
for ch_num, meta, text, dname in chapters:
    for tw in time_words:
        if tw in text:
            time_words[tw].append(ch_num)

for tw, chs in time_words.items():
    if chs:
        print(f'  {tw}: Ch{min(chs)}-Ch{max(chs)}, {len(chs)}章')

# ===== 6. EMOTIONAL BEATS =====
print()
print('='*50)
print('6. 章节长度异常')
print('='*50)
for ch_num, meta, text, dname in chapters:
    wc = meta.get('word_count', 0)
    if wc < 1200:
        print(f'  ⚠️ Ch{ch_num}: {wc}字 (偏短)')
    elif wc > 4000:
        print(f'  ⚠️ Ch{ch_num}: {wc}字 (偏长)')

# ===== 7. CHARACTER APPEARANCE GAPS =====
print()
print('='*50)
print('7. 主要角色出场分布')
print('='*50)
main_chars = ['沈夜','老白','沈万通','顾长明','钟国良','蒋继先','赵兰','许薇','赵铁面','孟小鱼']
for char_name in main_chars:
    chs = []
    for ch_num, meta, text, dname in chapters:
        if char_name in text:
            chs.append(ch_num)
    if chs:
        gaps = []
        for i in range(1, len(chs)):
            gap = chs[i] - chs[i-1]
            if gap > 10:
                gaps.append(f'Ch{chs[i-1]}→Ch{chs[i]}({gap}章)')
        gap_str = f' 缺口: {", ".join(gaps)}' if gaps else ''
        print(f'  {char_name}: Ch{min(chs)}-Ch{max(chs)}, {len(chs)}章{gap_str}')
    else:
        print(f'  {char_name}: ❌ 未出现')

print()
print('='*50)
print('审查完毕')
print('='*50)
