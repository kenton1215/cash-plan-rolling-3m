"""DeepSeek 大模型客户端 (OpenAI 兼容接口)

模型可通过环境变量 DEEPSEEK_MODEL 配置:
- deepseek-chat    官方快速对话模型(即"Flash"级轻量模型, 默认)
- deepseek-reasoner 深度思考模型
- 第三方代理(硅基流动/火山方舟等)的 flash 版本按代理方模型名填写

未配置 DEEPSEEK_API_KEY 时自动降级为规则引擎模式, 系统全部功能照常可用。
"""
import requests

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class LLMClient:
    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.model = DEEPSEEK_MODEL
        self.base_url = DEEPSEEK_BASE_URL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, max_tokens: int = 2500,
             temperature: float = 0.3, timeout: int = 120):
        """返回模型回复; 未配置Key或调用失败时返回None(由调用方降级)"""
        if not self.available:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "max_tokens": max_tokens, "temperature": temperature},
                timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None


_llm = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
