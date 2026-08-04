"""count_words 函数单测 - 覆盖中英文混排字数统计"""

import pytest

from moliu.engines.generator import count_words


class TestCountWords:
    """字数统计算法测试"""

    # === 纯中文测试 ===
    def test_empty_string(self):
        """空字符串返回 0"""
        assert count_words("") == 0

    def test_pure_chinese(self):
        """纯中文文本"""
        assert count_words("你好世界") == 4
        assert count_words("墨流 AI 小说创作") == 7  # 墨流 + AI + 小说创作 = 2 + 1 + 4 = 7

    def test_chinese_with_punctuation(self):
        """中文带标点（标点不计入）"""
        text = "林默看着系统面板上的倒计时。只剩三分钟。"
        # 林 默 看 着 系 统 面 板 上 的 倒 计 时 只 剩 三 分 钟 = 18
        assert count_words(text) == 18

    def test_chinese_special_characters(self):
        """中文特殊字符（如 emoji 不计入）"""
        assert count_words("🎉 你好 🚀") == 2  # 只有 你 好

    # === 纯英文测试 ===
    def test_pure_english(self):
        """纯英文文本"""
        assert count_words("Hello World") == 2
        assert count_words("AI Novel Writing Engine") == 4

    def test_english_case_insensitive(self):
        """英文大小写不敏感"""
        assert count_words("Hello hello HELLO") == 3

    def test_english_with_numbers(self):
        """英文带数字（数字不计入）"""
        assert count_words("Chapter 1") == 1  # 只有 Chapter

    def test_english_punctuation(self):
        """英文带标点"""
        assert count_words("Hello, World!") == 2

    # === 中英混合测试 ===
    def test_mixed_chinese_english(self):
        """中英混合"""
        assert count_words("Hello世界 Test测试") == 6  # Hello(1) + 世界(2) + Test(1) + 测试(2) = 6
        assert count_words("AI系统 小说Generator") == 6  # AI(1) + 系统(2) + 小说(2) + Generator(1) = 6

    def test_mixed_with_punctuation(self):
        """中英混合带标点"""
        text = "林默使用 AI 工具，生成了第 1 章的正文。"
        # 林 默 使 用 工 具 生 成 了 第 章 的 正 文 + AI = 15
        assert count_words(text) == 15

    # === CJK 扩展测试 ===
    def test_cjk_extension_a(self):
        """CJK 扩展 A 区字符（U+3400–U+4DBF）"""
        # 㐀 (U+3400) 是扩展 A 区的第一个字符
        assert count_words("㐀") == 1
        assert count_words("㐀䶿") == 2  # 䶿是扩展 A 区最后一个

    def test_cjk_basic(self):
        """CJK 基本区字符（U+4E00–U+9FFF）"""
        # 一 (U+4E00) 是基本区第一个
        # 鿿 (U+9FFF) 是基本区最后一个
        assert count_words("一") == 1
        assert count_words("鿿") == 1

    def test_cjk_extension_b_h(self):
        """CJK 扩展 B-H 区字符（当前实现不支持）"""
        # 𠀀 (U+20000) 是扩展 B 区字符
        # 当前实现的正则 [一-鿿㐀-䶿] 不包含扩展 B-H
        text = "𠀀"
        # 注意：当前实现会返回 0，这是已知局限
        result = count_words(text)
        assert result == 0  # 当前行为，待改进

    def test_rarer_chinese_characters(self):
        """生僻中文字符"""
        # 常用生僻字
        assert count_words("龘") == 1  # 三个龙
        assert count_words("靐") == 1  # 三个雷
        assert count_words("鱻") == 1  # 三个鱼

    # === 边界情况测试 ===
    def test_whitespace_only(self):
        """纯空白字符"""
        assert count_words("   \n\t  ") == 0

    def test_numbers_only(self):
        """纯数字（不计入）"""
        assert count_words("12345") == 0
        assert count_words("2024年") == 1  # 只有 年

    def test_punctuation_only(self):
        """纯标点符号"""
        assert count_words("。，！？、；：""''（）") == 0

    def test_very_long_text(self):
        """超长文本（性能测试）"""
        # 使用空格分隔英文单词
        text = "你好" * 1000 + " " + " Hello" * 1000
        assert count_words(text) == 2000 + 1000  # 2000 中文 + 1000 英文单词

    def test_emoji_only(self):
        """纯 emoji"""
        assert count_words("🎉🚀🌟") == 0

    def test_html_tags(self):
        """包含 HTML 标签"""
        text = "<p>你好 <strong>World</strong></p>"
        # 你 好 + World = 3
        assert count_words(text) == 3

    # === 实际小说文本测试 ===
    def test_novel_paragraph(self):
        """实际小说段落"""
        text = "林默看着系统面板上的倒计时。只剩三分钟。教室里全是人。他把面板关掉。又打开。字没变。"
        # 逐字统计：13+5+6+6+3+3 = 36
        assert count_words(text) == 36

    def test_dialog_with_english(self):
        """含英文的对话"""
        text = '"AI 说：你好世界。" 林默回答。'
        # AI + 说 你 好 世 界 林 默 回 答 = 10
        assert count_words(text) == 10
