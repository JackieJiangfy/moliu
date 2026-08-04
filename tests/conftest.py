"""pytest 配置文件 - 共享 fixture 和测试配置"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

from moliu.config import Config
from moliu.data.schemas import CharacterCard, CharacterCore, CharacterState, SpeechProfile, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager


# === 基础 Fixture ===
@pytest.fixture(scope="session")
def test_config():
    """测试用配置 - 使用内存路径，避免污染真实数据"""
    config = Config()
    # 覆盖路径到临时目录
    return config


@pytest.fixture(scope="session")
def prompts(test_config):
    """Prompt 管理器 fixture"""
    return PromptManager(test_config)


# === 角色卡 Fixture ===
@pytest.fixture
def empty_character():
    """空角色卡"""
    return CharacterCard(name="Test")


@pytest.fixture
def full_character():
    """完整角色卡"""
    return CharacterCard(
        name="林默",
        one_line_pitch="社恐程序员被系统逼成校园风云人物",
        speech_profile=SpeechProfile(
            style="简短理性",
            sentence_length="短句为主",
            tone="陈述多，感叹号少",
            common_words=["行", "嗯", "懂了"],
            banned_words=["真的吗", "太好了", "天啊"],
        ),
        speech_samples=[
            '"行。"（被要求做任务时）',
            '"分析过了。三个方案，第一种最快。"（遇到问题时）',
        ],
        inner_voice_style="代码注释式",
        core=CharacterCore(
            core_desire="掌控自己的人生",
            surface_desire="完成系统任务，变强",
            deep_fear="再次失去在乎的人",
            value_bottom_line=["不伤及无辜", "不用系统能力违法"],
        ),
        backstory_summary="8岁父母车祸去世，被姨妈养大",
        state=CharacterState(
            location="A市大学城3号宿舍楼512",
            current_goal="完成系统第5个任务",
            current_emotion="紧张但冷静",
        ),
    )


# === 世界观 Fixture ===
@pytest.fixture
def empty_world():
    """空世界观"""
    return WorldSetting()


@pytest.fixture
def full_world():
    """完整世界观"""
    return WorldSetting(
        era="现代都市大学",
        core_rules=["系统秘密存在", "能力与现实法则共存", "任务失败有惩罚"],
        power_system="等级制 F/E/D/C/B/A/S，完成任务积分升级",
        faction_summary="系统拥有者协会 + 普通人类社会",
        key_constraints=["不能直接杀人", "能力不能直接变现"],
        narrative_style="轻松吐槽，快节奏爽文",
    )


# === Mock Fixture ===
@pytest.fixture
def mock_gateway(mocker):
    """Mock 的 DeepSeekGateway - 不调用真实 API"""
    mock = AsyncMock(spec=DeepSeekGateway)
    mock.generate.return_value = ("测试响应内容", 100)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_httpx_client(mocker):
    """Mock 的 httpx AsyncClient"""
    mock = AsyncMock(spec=AsyncClient)
    return mock


# === 测试工具 Fixture ===
@pytest.fixture
def temp_dir(tmp_path):
    """临时目录 fixture"""
    return tmp_path


# === 自动使用 Fixture ===
@pytest.fixture(autouse=True)
def isolate_tests():
    """自动隔离测试 - 确保测试间互不影响"""
    original_env = {}
    import os
    for key in list(os.environ.keys()):
        if key.startswith("MO_"):
            original_env[key] = os.environ.pop(key)
    yield
    # 恢复环境变量
    os.environ.update(original_env)
