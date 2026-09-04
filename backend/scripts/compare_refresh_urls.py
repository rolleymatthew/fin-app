"""对比两个 URL 的 Set-Cookie 是否会改变 qgqp_b_id。"""
import asyncio
import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

INITIAL = (
    "qgqp_b_id=936abcacaf7b6912a66397a6aca63529; "
    "st_pvi=52571760823789; st_si=60738043625265"
)


async def fetch(url: str, referer: str | None = None, label: str = ""):
    headers = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as cli:
        # 先把已知 cookie 注入
        for kv in INITIAL.split(";"):
            k, v = kv.strip().split("=", 1)
            cli.cookies.set(k, v, domain=".eastmoney.com")
        before = "; ".join(f"{c.name}={c.value}" for c in cli.cookies.jar if c.value)
        r = await cli.get(url, headers=headers)
        after = "; ".join(f"{c.name}={c.value}" for c in cli.cookies.jar if c.value)
        set_cookie_headers = r.headers.get_list("set-cookie")
        new_qgqp = [c for c in set_cookie_headers if "qgqp_b_id" in c.lower()]
        print(f"\n--- {label} ---")
        print(f"URL: {url}")
        print(f"status: {r.status_code}")
        print(f"Set-Cookie headers ({len(set_cookie_headers)} total):")
        for sc in set_cookie_headers:
            print(f"  {sc[:200]}")
        print(f"qgqp_b_id相关: {new_qgqp}")
        print(f"cookie jar before: {before[:120]}...")
        print(f"cookie jar after : {after[:120]}...")
        print(f"是否变化: {'YES' if before != after else 'NO'}")


async def main():
    urls = [
        ("https://www.eastmoney.com/", None, "1) 主页 www.eastmoney.com"),
        ("https://quote.eastmoney.com/sh510300.html", None, "2) 行情页 sh510300"),
        ("https://quote.eastmoney.com/sh510050.html", None, "3) 行情页 sh510050"),
        (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&beg=0&end=20500101&secid=1.510050&klt=101&fqt=0&ut=fa5fd1943c7b386f172d6893dbfba10b&smplmt=1000000&lmt=1000000&_=1784584900450",
            "https://quote.eastmoney.com/sh510050.html",
            "4) kline API + referer",
        ),
    ]
    for url, ref, label in urls:
        try:
            await fetch(url, ref, label)
        except Exception as exc:
            print(f"\n{label}: ERROR {exc}")


if __name__ == "__main__":
    asyncio.run(main())