"""TDX vipdata daily fetcher constants.

URLs and on-disk filenames shared between the fetcher, admin API, and CLI.
Defaults match the official 通达信 个人版 data CDN.
"""

# 个人版盘后日线包 (全量, ~525MB / 12420 files, deflate 压缩)
DOWNLOAD_URL: str = "https://data.tdx.com.cn/vipdoc/hsjday.zip"

# 同站点元信息 JS (暴露 HSJDAY_SOFT_TIME / HSJDAY_SOFT_SIZE)
META_URL: str = "https://data.tdx.com.cn/vipdoc/_hsjdayinfo.js"

# on-disk names
HSJDAY_ZIP_NAME: str = "hsjday.zip"
VIPDOC_SUBDIR: str = "vipdoc"
LAST_FETCH_FILENAME: str = ".last_fetch.json"

# 下载时给 TDX CDN 的 Referer (部分镜像会校验)
REFERER: str = "https://www.tdx.com.cn/article/vipdata.html"
USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) fin-app/fetcher"