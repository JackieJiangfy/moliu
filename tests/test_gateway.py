"""Gateway 单元测试 - 覆盖 4 类异常重试"""

import pytest
from httpx import HTTPStatusError, TimeoutException

from moliu.config import Config
from moliu.engines.gateway import DeepSeekAPIError, DeepSeekGateway, _RetryIfServerError


class TestRetryLogic:
    """重试逻辑单元测试"""

    def test_retry_if_server_error_5xx(self):
        """5xx 服务器错误应该重试"""
        from unittest.mock import MagicMock

        exc = HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        # 模拟 tenacity 的 RetryCallState
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is True

    def test_retry_if_server_error_429(self):
        """429 限流错误应该重试"""
        from unittest.mock import MagicMock

        exc = HTTPStatusError(
            "Too Many Requests",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is True

    def test_retry_if_server_error_4xx(self):
        """4xx 客户端错误不应该重试"""
        from unittest.mock import MagicMock

        exc = HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=MagicMock(status_code=401),
        )
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is False

    def test_retry_if_server_error_timeout(self):
        """TimeoutException 应该重试"""
        from unittest.mock import MagicMock

        exc = TimeoutException("Timeout")
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is True

    def test_retry_if_server_error_connect_error(self):
        """ConnectError 网络连接错误应该重试"""
        from unittest.mock import MagicMock
        from httpx import ConnectError

        exc = ConnectError("Connection Refused")
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is True

    def test_retry_if_server_error_read_error(self):
        """ReadError 读取错误应该重试"""
        from unittest.mock import MagicMock
        from httpx import ReadError

        exc = ReadError("Read Error")
        attempt = MagicMock()
        attempt.outcome.exception.return_value = exc

        retry = _RetryIfServerError()
        assert retry(attempt) is True

    def test_retry_if_success(self):
        """成功的调用不应该触发重试判断"""
        from unittest.mock import MagicMock

        attempt = MagicMock()
        attempt.outcome.exception.return_value = None

        retry = _RetryIfServerError()
        assert retry(attempt) is False


class TestGatewayBasics:
    """Gateway 基础功能测试"""

    def test_gateway_init(self):
        """Gateway 初始化"""
        config = Config()
        gw = DeepSeekGateway(config)
        assert gw is not None
        assert gw.config == config
        # 验证客户端已创建
        assert hasattr(gw, '_client')

    def test_deepseek_api_error(self):
        """DeepSeekAPIError 消息处理"""
        try:
            raise DeepSeekAPIError("test error message")
        except DeepSeekAPIError as e:
            assert "test error message" in str(e)

    def test_deepseek_api_error_inherits_from_exception(self):
        """DeepSeekAPIError 继承自 Exception"""
        assert issubclass(DeepSeekAPIError, Exception)

    def test_config_defaults(self):
        """验证配置默认值"""
        config = Config()
        assert config.deepseek_max_retries >= 1
        assert config.deepseek_timeout > 0
        assert config.deepseek_base_url is not None
