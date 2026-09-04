from __future__ import annotations

from pathlib import Path
from typing import List


def write_file(filepath: str, filename: str, text: str, encoding: str = "gbk") -> None:
    Path(filepath).mkdir(parents=True, exist_ok=True)
    path = Path(filepath) / filename
    path.write_text(text, encoding=encoding)


def write_file_path(file_path: str, content: str, encoding: str = "utf-8") -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


def exists_and_is_file(filename: str) -> bool:
    path = Path(filename)
    return path.exists() and path.is_file()


def mkdirs(filename: str) -> None:
    Path(filename).mkdir(parents=True, exist_ok=True)


def get_files_of_directory(dir_path: str) -> List[str]:
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return []
    names = [p.name for p in path.iterdir()]
    return sorted(names, reverse=True)


def get_files_of_dir_by_ext(dir_path: str, prefix: str | None, ext: str | None) -> List[str]:
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return []
    files = []
    for p in path.iterdir():
        name = p.name
        if prefix and ext and name.lower().startswith(prefix.lower()) and name.lower().endswith(ext.lower()):
            files.append(name)
        elif prefix and not ext and name.lower().startswith(prefix.lower()):
            files.append(name)
        elif ext and not prefix and name.lower().endswith(ext.lower()):
            files.append(name)
        elif not prefix and not ext:
            files.append(name)
    return sorted(files, reverse=True)


def read_file_as_list_of_strings(filename: str, charset: str) -> List[str]:
    return Path(filename).read_text(encoding=charset).splitlines()
