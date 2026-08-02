# LLMs/deepseek package — DeepSeek provider scripts for agent use.
#
# This subfolder contains everything the agents need to talk to DeepSeek:
#   provider.py  → LLMResult, DeepSeekProvider (live), MockProvider (offline)
#
# Consumers should import through the package (or LLMs.api facade):
#   from LLMs.deepseek import DeepSeekProvider, MockProvider, LLMResult
from LLMs.deepseek.provider import LLMResult, DeepSeekProvider, MockProvider

__all__ = ["LLMResult", "DeepSeekProvider", "MockProvider"]
