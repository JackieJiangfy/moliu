"""检查第10章具体问题段落"""
from pathlib import Path
from moliu.deai.detector import DeAIDetector

text = Path("output/chapters/第10章/正文.md").read_text(encoding="utf-8")
d = DeAIDetector()
r = d.detect_l1(text)
print(f"=== 第10章 详细问题 ===")
print(f"  总分: {r.overall_score:.2f}")
print(f"  命中: {r.tic_counts}")
print(f"  字数: {len(text)}")
print()
for para, pattern, line in r.flagged_paragraphs:
    print(f"  L{line} [{pattern}]")
    print(f"  内容: {para}")
    print()

# 检查AI感受解释
import re
FEELING_PATTERNS = [
    r'像在[^，。]{2,15}',
    r'像是[^，。\n]{2,15}的[^，。\n]{2,15}',
    r'仿佛[^，。\n]{2,20}',
    r'似乎在[^，。\n]{2,15}',
    r'像一只[^，。\n]{2,10}的眼',
]
print("=== 感受解释候选 ===")
for p in FEELING_PATTERNS:
    for m in re.finditer(p, text):
        # 获取上下文
        start = max(0, m.start()-20)
        end = min(len(text), m.end()+20)
        print(f"  {text[start:end]}")
