"""
IPP_Social — the Multi Agent platform module (independent).

A single unified IPP node (IPP.json + IPP_object.py + IPP_executor.py)
with 11 channels. Γ construction: IPP_Social/social_node.py. Platform
assembly: IPP_Social/platform.py.

    from IPP_Social.platform import build_platform
    from IPP_Social.social_node import social_node
"""


def __getattr__(name):
    if name == "build_platform":
        from IPP_Social.platform import build_platform
        return build_platform
    if name == "social_node":
        from IPP_Social.social_node import social_node
        return social_node
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["build_platform", "social_node"]
