"""批量检查所有章节：去AI味+破折号+常见AI模式"""
import re
from pathlib import Path
from moliu.deai.detector import DeAIDetector

d = DeAIDetector()

# AI感受解释模式
FEELING_PATTERNS = [
    r'像在确认[^，。]*',
    r'像是[^，。\n]{2,15}的[^，。\n]{2,15}',
    r'仿佛[^，。\n]{2,20}',
    r'似乎在[^，。\n]{2,15}',
]

# 万能结尾
ENDING_PATTERNS = [
    r'明天，又是新的一天',
    r'像[^，。\n]{2,10}的眼睛',
    r'像一只[^，。\n]{2,10}的眼',
]

print(f"{'章':<4} {'字数':<6} {'分数':<6} {'破折号':<6} {'命中模式':<30} 问题")
print("-" * 100)

for i in range(1, 16):
    path = Path(f"output/chapters/第{i}章/正文.md")
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    
    # 去AI味检测
    r = d.detect_l1(text)
    
    # 破折号计数
    dash_count = text.count("——")
    
    # AI感受解释
    feeling_hits = []
    for p in FEELING_PATTERNS:
        matches = re.findall(p, text)
        feeling_hits.extend(matches[:2])
    
    # 万能结尾
    ending_hits = []
    for p in ENDING_PATTERNS:
        if re.search(p, text[-100:]):
            ending_hits.append(p)
    
    # 检查"明天，又是新的一天"
    has_bad_ending = "明天，又是新的一天" in text[-200:]
    
    issues = []
    if r.overall_score < 0.95:
        issues.append(f"低分{r.overall_score:.2f}")
    if dash_count > 5:
        issues.append(f"破折号{dash_count}")
    if feeling_hits:
        issues.append(f"感受解释×{len(feeling_hits)}")
    if has_bad_ending:
        issues.append("万能结尾")
    
    tic_str = ",".join([f"{k}:{v}" for k,v in r.tic_counts.items()]) if r.tic_counts else "-"
    issue_str = "|".join(issues) if issues else "✓"
    
    print(f"{i:<4} {len(text):<6} {r.overall_score:<6.2f} {dash_count:<6} {tic_str:<30} {issue_str}")

print("\n=== 详细问题段落 ===")
for i in range(1, 16):
    path = Path(f"output/chapters/第{i}章/正文.md")
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    r = d.detect_l1(text)
    if r.flagged_paragraphs:
        print(f"\n第{i}章:")
        for para, pattern, line in r.flagged_paragraphs:
            print(f"  L{line} [{pattern}] {para[:60]}")
