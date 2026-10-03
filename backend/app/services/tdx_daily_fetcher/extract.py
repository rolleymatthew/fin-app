"""原子解压: zip → <target>/vipdoc.tmp/ → shutil.move → <target>/vipdoc/.

失败保证:
  - zip 解压失败 → vipdoc.tmp/ 删除, 原 vipdoc/ 不动
  - shutil.move 失败 (罕见, 跨盘符会触发) → vipdoc.tmp/ 删除
  - 任何阶段抛错统一包装成 ExtractError

代价: 解压中磁盘峰值 ×2 (zip + 旧 vipdoc + 新 vipdoc.tmp).
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from app.services.tdx_daily_fetcher.constants import VIPDOC_SUBDIR
from app.services.tdx_daily_fetcher.exceptions import ExtractError


def atomic_extract_zip(zip_path: Path, target_dir: Path) -> int:
    """解压 zip 到 target_dir/vipdoc/ (tmp + rename 保证失败时原目录不变).

    Args:
        zip_path: 已下载的 zip 文件
        target_dir: 解压根目录 (zip 自身也保留在此)

    Returns:
        解压的文件数

    Raises:
        ExtractError: zip 损坏 / IO 失败 / move 失败
    """
    if not zip_path.is_file():
        raise ExtractError(f"zip 文件不存在: {zip_path}")

    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir / f"{VIPDOC_SUBDIR}.tmp"
    final_dir = target_dir / VIPDOC_SUBDIR

    # 清理上次残留的 .tmp (上次中途崩了)
    if tmp_dir.is_dir():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise ExtractError(f"zip 损坏: {bad}")
            # 兜底: 通达信 zip 把路径分隔符写成 '\' (Windows 风格) 而非 ZIP 标准的 '/'.
            # Python zipfile._sanitize_filename 仅在 os.sep='\\' (即 Windows) 时把
            # '\' 转 '/'; Docker 容器是 Linux, os.sep='/', 不转换, extractall 会把
            # 'bj\lday\bj000001.day' 当成单文件名, bind mount 到 NTFS 时驱动层把
            # '\' 替换成 U+F05C 等私有区字符, 整盘 12449 个文件平铺带乱码.
            #
            # 注意: 必须用 z.extractall(path, members=z.infolist()) 而非裸 z.extractall(path).
            # 后者默认从 self.namelist() 拿字符串名, 内部 _extract_member 会调
            # self.getinfo(name), 但 NameToInfo 的 key 是 zip 原始的 '\' 分隔名 (没跟着
            # patch 改), 改成 '/' 后 getinfo 会 KeyError: "There is no item named ..."
            # 显式传 ZipInfo 列表让 _extract_member 走 isinstance(member, ZipInfo) 分支
            # 跳过 getinfo, 直接用我们 patch 过的 info.filename.
            for info in z.infolist():
                if "\\" in info.filename:
                    info.filename = info.filename.replace("\\", "/")
            z.extractall(tmp_dir, members=z.infolist())
        # 整个 vipdoc/ 是 zip 内的顶级目录; tmp_dir 已经是 vipdoc 内容
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        shutil.move(str(tmp_dir), str(final_dir))
    except ExtractError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ExtractError(f"解压失败: {exc}") from exc
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ExtractError(f"解压失败: {exc}") from exc

    # 统计: 数 final_dir 下的所有文件
    count = sum(1 for _ in final_dir.rglob("*") if _.is_file())
    return count