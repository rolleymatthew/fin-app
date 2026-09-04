"""用用户提供的 cookie 测试东财 K 线接口是否可用。"""
import asyncio
import sys
import time

import httpx

COOKIE = (
    "qgqp_b_id=936abcacaf7b6912a66397a6aca63529; "
    "st_nvi=tXrLpHnWn3BzHBUM_Wwzvae17; "
    "nid18=0e017686c42bed90861dd15e68cbd507; "
    "nid18_create_time=1779982945297; "
    "gviem=W6aBbK60XeNANxYmXrSo_d5da; "
    "gviem_create_time=1779982945297; "
    "st_si=60738043625265; "
    "st_asi=delete; "
    "fullscreengg=1; "
    "fullscreengg2=1; "
    "rskey=jFYsEdWdVM1lmVG03cXFhU3VZK0xJRWtwUT09EfckO; "
    "p_origin=https%3A%2F%2Fpassport2.eastmoney.com; "
    "st_pvi=52571760823789; "
    "st_sp=2026-05-01%2010%3A25%3A45; "
    "st_inirUrl=https%3A%2F%2Fwww.eastmoney.com%2F; "
    "st_sn=8; "
    "st_psi=20260721055917800-0-5688222358"
)

HOSTS = [
    "https://push2his.eastmoney.com",
    "https://push2.eastmoney.com",
]

PARAMS_BASE = {
    "fields1": "f1,f2,f3,f4,f5,f6",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    "beg": 0,
    "end": 20991231,
    "klt": 101,
    "fqt": 1,
    "smplmt": 1000000,
    "lmt": 1000000,
    "ut": "fa5fd1943c7b386f172d6893dbfba10b",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


async def hit(host: str, secid: str, code: str):
    prefix = "sz" if secid.startswith("0.") else "sh"
    referer = f"https://quote.eastmoney.com/{prefix}{code}.html"
    params = {**PARAMS_BASE, "secid": secid, "_": int(time.time() * 1000)}
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": referer,
        "Cookie": COOKIE,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-dest": "script",
        "pragma": "no-cache",
    }
    url = f"{host}/api/qt/stock/kline/get"
    t0 = time.time()
    async with httpx.AsyncClient(timeout=20, http2=False) as cli:
        r = await cli.get(url, params=params, headers=headers)
    dt = time.time() - t0
    return r, dt


async def main():
    targets = [
        ("1.510300", "510300", "上证300ETF"),
        ("0.159915", "159915", "创业板ETF"),
    ]
    for secid, code, name in targets:
        print(f"\n=== {name} secid={secid} ===")
        for host in HOSTS:
            try:
                r, dt = await hit(host, secid, code)
                preview = r.text[:240].replace("\n", " ")
                print(f"host={host} status={r.status_code} elapsed={dt:.2f}s")
                print(f"  preview: {preview}")
                if r.status_code == 200 and ("klines" in r.text or "data" in r.text):
                    if '"klines"' in r.text and '"rc"' in r.text:
                        rc_idx = r.text.find('"rc":')
                        print(f"  rc段: ...{r.text[max(0, rc_idx-2):rc_idx+60]}...")
                    return 0
            except Exception as exc:
                print(f"host={host} ERROR: {exc}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))