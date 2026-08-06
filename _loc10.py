"""精确定位第10章的强行对仗"""
from pathlib import Path
from moliu.deai.detector import DeAIDetector

text = Path("output/chapters/第10章/正文.md").read_text(encoding="utf-8")
d = DeAIDetector()
r = d.detect_l1(text)
print(f"=== 第10章 flagged段落 ===")
for para, pattern, line in r.flagged_paragraphs:
    print(f"\nL{line} [{pattern}]")
    print(f"内容: {para}")
    print(f"长度: {len(para)}")
