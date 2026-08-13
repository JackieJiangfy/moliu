"""Check continuity and logic issues across all 125 chapters"""
import json, re
from pathlib import Path
from collections import Counter

CHAPTERS_DIR = Path('output/chapters')

def all_chapters():
    dirs = sorted(CHAPTERS_DIR.glob('第*章'), key=lambda d: int(re.search(r'\d+', d.name).group()))
    meta_files = [(d, d / 'meta.json', d / '正文.md') for d in dirs if (d / '正文.md').exists()]
    results = []
    for d, mf, tf in meta_files:
        meta = json.loads(mf.read_text(encoding='utf-8'))
        text = tf.read_text(encoding='utf-8')
        ch_num = meta['chapter_num']
        results.append((ch_num, meta, text, d))
    return results

def check_last_sentence_next_first(chapters):
    """Check if last sentence of chapter N connects to first sentence of chapter N+1"""
    issues = []
    for i in range(len(chapters) - 1):
        ch_curr, _, text_curr, _ = chapters[i]
        ch_next, _, text_next, _ = chapters[i+1]
        # Get last non-empty line of current
        lines_curr = [l.strip() for l in text_curr.split('\n') if l.strip()]
        lines_next = [l.strip() for l in text_next.split('\n') if l.strip()]
        if lines_curr and lines_next:
            last = lines_curr[-1][:80]
            first = lines_next[0][:80]
            # Just report for manual review
            issues.append((ch_curr, ch_next, last, first))
    return issues

def check_keyword_patterns(chapters):
    """Check for potential issues: inconsistent death states, missing characters, etc."""
    issues = []
    for ch_num, meta, text, _ in chapters:
        # Check if key_characters list seems complete
        kc = meta.get('key_characters', [])
        # Check for markdown headers that shouldn't be there
        if re.search(r'^## 第[百零一二三四五六七八九十\d]+章', text, re.MULTILINE):
            issues.append((ch_num, 'HEADER', 'Contains markdown chapter header'))
        # Check for very short chapters
        wc = meta.get('word_count', 0)
        if wc < 1000:
            issues.append((ch_num, 'SHORT', f'Only {wc} words'))
        if wc > 4000:
            issues.append((ch_num, 'LONG', f'{wc} words, may be bloated'))
    return issues

def check_character_name_consistency(chapters):
    """Check 曹桂兰's daughter name consistency: 陈念 vs 许薇 vs 陈秀莲"""
    names = {}
    for ch_num, meta, text, _ in chapters:
        for name in ['陈念', '许薇', '陈秀莲', '曹桂兰']:
            count = text.count(name)
            if count > 0:
                names.setdefault(name, []).append(ch_num)
    return names

chapters = all_chapters()
print(f'Total chapters: {len(chapters)}')
print()

# Word count stats
wcs = [c[1]['word_count'] for c in chapters]
print(f'=== 字数统计 ===')
print(f'Total: {sum(wcs):,}')
print(f'Avg: {sum(wcs)//len(wcs):,}/章')
min_wc, min_ch = min((w, ch[0]) for w, ch in zip(wcs, chapters))
max_wc, max_ch = max((w, ch[0]) for w, ch in zip(wcs, chapters))
print(f'Min: Ch{min_ch} = {min_wc:,}字')
print(f'Max: Ch{max_ch} = {max_wc:,}字')
print()

# 1. Continuity between chapters
print('=== 章节衔接 (末句 -> 次章首句) ===')
transitions = check_last_sentence_next_first(chapters)
# Only show notable gaps (where the connection seems broken)
for ch, nxt, last, first in transitions:
    # Show first 3 and last 3, and every 20th
    if ch <= 3 or ch >= 120 or ch % 20 == 0:
        print(f'  Ch{ch}末: {last}')
        print(f'  Ch{nxt}首: {first}')
        print()

# 2. Keyword issues
print('=== 格式/长度问题 ===')
fmt_issues = check_keyword_patterns(chapters)
for ch, typ, msg in fmt_issues:
    print(f'  Ch{ch} [{typ}]: {msg}')
print()

# 3. Name consistency
print('=== 曹桂兰女儿名字分布 ===')
name_dist = check_character_name_consistency(chapters)
for name, chs in sorted(name_dist.items()):
    print(f'  {name}: 出现在 Ch{min(chs)}-Ch{max(chs)}, 共{len(chs)}章')
print()

# 4. Key characters per chapter analysis
print('=== 关键角色出场频率 ===')
char_freq = Counter()
for ch_num, meta, _, _ in chapters:
    for c in meta.get('key_characters', []):
        char_freq[c] += 1
for name, count in char_freq.most_common(15):
    print(f'  {name}: {count}章')

print()
print('=== 检查完毕 ===')
print('需要人工审查的项目:')
print('  1. 每章末句与下章首句的衔接（已列出Ch1-3, Ch120-125）')
print('  2. 钟国良人设一致性（Ch105反派 vs Ch109八十七亿非赃款）')
print('  3. Ch108->109->110 电话线连续性')
print('  4. 曹桂兰女儿名字统一（陈念/许薇/陈秀莲是否混用）')
