"""Config 章节目录命名工具的单测 — chapter_dir_name / parse_chapter_num"""

import pytest

from moliu.config import Config


class TestChapterDirName:
    """Config.chapter_dir_name — 章节号 → 目录名"""

    def test_single_digit(self):
        assert Config.chapter_dir_name(1) == "chapter_0001"

    def test_double_digit(self):
        assert Config.chapter_dir_name(10) == "chapter_0010"

    def test_triple_digit(self):
        assert Config.chapter_dir_name(100) == "chapter_0100"

    def test_large_number(self):
        assert Config.chapter_dir_name(9999) == "chapter_9999"

    def test_zero(self):
        # 0 章虽不合法,但函数应当能稳定输出
        assert Config.chapter_dir_name(0) == "chapter_0000"

    def test_dict_order_equals_numeric_order(self):
        """字典序与数值序一致 — 这是改造的核心目的"""
        nums = [1, 2, 9, 10, 11, 100, 101, 999, 1000]
        names = [Config.chapter_dir_name(n) for n in nums]
        # 字典序排序后应等于原顺序(已升序)
        assert sorted(names) == names


class TestParseChapterNum:
    """Config.parse_chapter_num — 目录名 → 章节号(兼容新旧格式)"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("chapter_0001", 1),
            ("chapter_0010", 10),
            ("chapter_0100", 100),
            ("chapter_9999", 9999),
        ],
    )
    def test_new_format(self, name, expected):
        assert Config.parse_chapter_num(name) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("第1章", 1),
            ("第10章", 10),
            ("第100章", 100),
        ],
    )
    def test_legacy_format(self, name, expected):
        """旧格式兼容 — 迁移前老用户的目录还能被识别"""
        assert Config.parse_chapter_num(name) == expected

    @pytest.mark.parametrize(
        "invalid",
        [
            "",
            "chapter_",
            "chapter_abc",
            "第章",
            "第x章",
            "chapter-0001",
            "CHAPTER_0001",
            "random_dir",
            "第1章 ",  # 带空格
        ],
    )
    def test_invalid_returns_none(self, invalid):
        assert Config.parse_chapter_num(invalid) is None

    def test_roundtrip(self):
        """chapter_dir_name ↔ parse_chapter_num 互逆"""
        for n in [1, 10, 100, 9999]:
            assert Config.parse_chapter_num(Config.chapter_dir_name(n)) == n
