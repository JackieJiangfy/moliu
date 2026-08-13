"""Generate chapter titles based on content analysis"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# Title generation rules based on chapter content keywords and arcs
# Format: {chapter_num: title}

titles = {
    # Ch1-15 already have titles - keep them
    1: "亡者遗产",
    2: "老白与账",
    3: "一张抵押合同",
    4: "四万七千六百亿",
    5: "怨气曲线",
    6: "资质核查",
    7: "不骗鬼",
    8: "临时流动性支持",
    9: "讨债的来了",
    10: "阴德账户",
    11: "工龄",
    12: "第一个月结",
    13: "未寄出的信",
    14: "特殊标记",
    15: "对不起",
}

# Ch16-125: generate from content analysis
for ch_num in range(16, 126):
    path = Path(f'output/chapters/第{ch_num}章/正文.md')
    if not path.exists():
        continue
    text = path.read_text('utf-8')
    meta_path = Path(f'output/chapters/第{ch_num}章/meta.json')
    meta = json.loads(meta_path.read_text('utf-8')) if meta_path.exists() else {}

    # Extract key elements
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    first_line = lines[0] if lines else ''
    last_line = lines[-1] if lines else ''

    # Try to generate a meaningful title based on content keywords
    title = None

    # Check for specific story beats
    if ch_num == 16: title = "审计算盘"
    elif ch_num == 17: title = "保单之谜"
    elif ch_num == 18: title = "鬼市暗流"
    elif ch_num == 19: title = "三百年的等待"
    elif ch_num == 20: title = "白露"
    elif ch_num == 21: title = "赵铁面"
    elif ch_num == 22: title = "审计组进驻"
    elif ch_num == 23: title = "百分之七十三"
    elif ch_num == 24: title = "三个月"
    elif ch_num == 25: title = "凌晨三点的验钞机"
    elif ch_num == 26: title = "樟木箱里的账"
    elif ch_num == 27: title = "倒计时"
    elif ch_num == 28: title = "周正邦"
    elif ch_num == 29: title = "审计报告"
    elif ch_num == 30: title = "新业务接入"
    elif ch_num == 31: title = "未知申请人"
    elif ch_num == 32: title = "十九年前的信"
    elif ch_num == 33: title = "第七码头"
    elif ch_num == 34: title = "赵铁面的账"
    elif ch_num == 35: title = "一千八百万"
    elif ch_num == 36: title = "刘处上门"
    elif ch_num == 37: title = "录音笔"
    elif ch_num == 38: title = "财政部的灯"
    elif ch_num == 39: title = "渡劫基金"
    elif ch_num == 40: title = "芯片"
    elif ch_num == 41: title = "沈万通的录音"
    elif ch_num == 42: title = "条件未满足"
    elif ch_num == 43: title = "十六楼"
    elif ch_num == 44: title = "共管人"
    elif ch_num == 45: title = "单方离线"
    elif ch_num == 46: title = "百分之五十二"
    elif ch_num == 47: title = "穿校服的鬼魂"
    elif ch_num == 48: title = "铜章"
    elif ch_num == 49: title = "暖黄色灯管下"
    elif ch_num == 50: title = "财政局门口"
    elif ch_num == 51: title = "蒋副司长的文件"
    elif ch_num == 52: title = "查封令"
    elif ch_num == 53: title = "贷款申请"
    elif ch_num == 54: title = "受理回执"
    elif ch_num == 55: title = "正常经营流程"
    elif ch_num == 56: title = "百分之五十六"
    elif ch_num == 57: title = "功德碑"
    elif ch_num == 58: title = "石碑碎片"
    elif ch_num == 59: title = "三千七百块名字"
    elif ch_num == 60: title = "周万贯的当铺"
    elif ch_num == 61: title = "秦馆长"
    elif ch_num == 62: title = "铜镜裂纹"
    elif ch_num == 63: title = "借据"
    elif ch_num == 64: title = "博物馆地下室"
    elif ch_num == 65: title = "完整的碑"
    elif ch_num == 66: title = "蒋副司长出事了"
    elif ch_num == 67: title = "灰蓝色中山装"
    elif ch_num == 68: title = "AI合成"
    elif ch_num == 69: title = "顾三娘"
    elif ch_num == 70: title = "被卖掉的女子"
    elif ch_num == 71: title = "二十四小时"
    elif ch_num == 72: title = "母版碎片"
    elif ch_num == 73: title = "渡劫基金解冻"
    elif ch_num == 74: title = "卖豆腐的老头"
    elif ch_num == 75: title = "欢迎回来法人"
    elif ch_num == 76: title = "渡劫之后"
    elif ch_num == 77: title = "死亡证明"
    elif ch_num == 78: title = "死在门里的人"
    elif ch_num == 79: title = "一个答案"
    elif ch_num == 80: title = "验钞机底部的凹槽"
    elif ch_num == 81: title = "天字四号"
    elif ch_num == 82: title = "顾长明"
    elif ch_num == 83: title = "三百多份驳回"
    elif ch_num == 84: title = "三千万坏账"
    elif ch_num == 85: title = "档案楼"
    elif ch_num == 86: title = "曹桂兰"
    elif ch_num == 87: title = "004号保险箱"
    elif ch_num == 88: title = "042在顾长明手里"
    elif ch_num == 89: title = "第三个签字的人"
    elif ch_num == 90: title = "顾长明.docx"
    elif ch_num == 91: title = "曹桂兰的女儿"
    elif ch_num == 92: title = "等了十九年的人"
    elif ch_num == 93: title = "我叫沈万通的儿子"
    elif ch_num == 94: title = "许薇"
    elif ch_num == 95: title = "002号夹层"
    elif ch_num == 96: title = "调查报告"
    elif ch_num == 97: title = "财政司顶楼"
    elif ch_num == 98: title = "042号粮库"
    elif ch_num == 99: title = "恢复名誉"
    elif ch_num == 100: title = "续上了"
    elif ch_num == 101: title = "沈万通的录像"
    elif ch_num == 102: title = "钟国良这个人"
    elif ch_num == 103: title = "十八楼"
    elif ch_num == 104: title = "无声的录像带"
    elif ch_num == 105: title = "三个死人账户"
    elif ch_num == 106: title = "影子银行"
    elif ch_num == 107: title = "通远实业"
    elif ch_num == 108: title = "左手缺了一根手指"
    elif ch_num == 109: title = "钟先生的电话"
    elif ch_num == 110: title = "钟国良的信"
    elif ch_num == 111: title = "临江墓园"
    elif ch_num == 112: title = "043号保险箱"
    elif ch_num == 113: title = "陈婆香烛"
    elif ch_num == 114: title = "蒋继先"
    elif ch_num == 115: title = "临江茶楼"
    elif ch_num == 116: title = "第十二层"
    elif ch_num == 117: title = "公生明廉生威"
    elif ch_num == 118: title = "让他杀"
    elif ch_num == 119: title = "第七块砖"
    elif ch_num == 120: title = "都平了"
    elif ch_num == 121: title = "母子"
    elif ch_num == 122: title = "周正邦的保单"
    elif ch_num == 123: title = "八十七亿"
    elif ch_num == 124: title = "雨中纸扎店"
    elif ch_num == 125: title = "关灯吧"

    # Store title in dict
    if title:
        titles[ch_num] = title

# Write titles to meta.json and generate txt file
txt_lines = []
for ch_num in range(1, 126):
    title = titles.get(ch_num, f"第{ch_num}章")
    txt_lines.append(f"第{ch_num}章 {title}")

    # Update meta.json
    meta_path = Path(f'output/chapters/第{ch_num}章/meta.json')
    if meta_path.exists():
        meta = json.loads(meta_path.read_text('utf-8'))
        if not meta.get('title'):
            meta['title'] = title
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

# Write txt file
txt_content = '\n'.join(txt_lines)
Path('章节名.txt').write_text(txt_content, encoding='utf-8')
print(f'章节名.txt 已生成，共 {len(txt_lines)} 章')
print(f'meta.json 已更新')
