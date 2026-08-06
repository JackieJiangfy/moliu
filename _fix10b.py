"""修复第10章：强行对仗+感受解释"""
from pathlib import Path
from moliu.deai.detector import DeAIDetector

path = Path("output/chapters/第10章/正文.md")
text = path.read_text(encoding="utf-8")

# 1. 修复感受解释
fixes = [
    # 感受解释1
    ('老白跟在他后面，飘得比平时慢，像在琢磨什么事。',
     '老白跟在他后面，飘得比平时慢。'),
    # 感受解释2
    ('她看着他，眼神跟昨天不太一样，像是在看一个不太理解但也没打算反驳的东西。过了几秒，她开口',
     '她看着他，眼神跟昨天不太一样。过了几秒，她开口'),
]

for old, new in fixes:
    if old in text:
        text = text.replace(old, new)
        print(f"修复: {old[:30]}...")

# 2. 查找强行对仗
import re
# 常见对仗模式：不是...是... / 没有...只有... / 一边...一边...
patterns = [
    (r'不是[^，。\n]{2,20}[，。][^，。\n]{0,10}是[^，。\n]{2,20}', "不是...是..."),
    (r'没有[^，。\n]{2,15}[，。][^，。\n]{0,10}只有[^，。\n]{2,15}', "没有...只有..."),
]

print("\n=== 对仗候选 ===")
for p, name in patterns:
    for m in re.finditer(p, text):
        start = max(0, m.start()-10)
        end = min(len(text), m.end()+10)
        print(f"  [{name}] {text[start:end]}")

path.write_text(text, encoding="utf-8")

d = DeAIDetector()
r = d.detect_l1(text)
print(f"\n=== 第10章 修复后 ===")
print(f"  总分: {r.overall_score:.2f}")
print(f"  命中: {r.tic_counts}")
print(f"  字数: {len(text)}")
for para, pattern, line in r.flagged_paragraphs:
    print(f"  L{line} [{pattern}] {para[:60]}")
