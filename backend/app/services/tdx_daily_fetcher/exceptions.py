"""TDX fetcher exception hierarchy.

所有失败用 FetchError 基类,子类按失败阶段细分,便于上层 / API 区分提示.
"""


class FetchError(Exception):
    """下载/解压流程任意阶段失败时抛. message 包含可直接呈现给用户的描述."""


class MetaParseError(FetchError):
    """_hsjdayinfo.js 不可达或格式变更."""


class DownloadError(FetchError):
    """zip 下载中断 / testzip 校验失败."""


class ExtractError(FetchError):
    """解压失败 (zip 损坏 / 磁盘满 / 权限不足)."""


class DiskSpaceError(ExtractError):
    """解压前磁盘预检不通过."""