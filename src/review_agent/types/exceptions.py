"""项目异常类型层次。

所有自定义异常继承自 ReviewAgentError，外部调用异常包装为对应子类。
"""


class ReviewAgentError(Exception):
    """项目基础异常，所有自定义异常的基类。"""


class ConfigError(ReviewAgentError):
    """配置加载或验证错误。"""


class DatabaseError(ReviewAgentError):
    """数据库操作错误。"""


class AIProviderError(ReviewAgentError):
    """AI 服务调用错误（超时、熔断、无效响应）。"""


class GitProviderError(ReviewAgentError):
    """Git 平台 API 调用错误。"""


class WebhookValidationError(ReviewAgentError):
    """Webhook 签名验证或事件处理错误。"""


class NotFoundError(ReviewAgentError):
    """资源不存在错误。"""


class ValidationError(ReviewAgentError):
    """数据验证错误。"""
