"""시세 읽기: ``날짜 키 값`` 한 줄씩 (공백·쉼표·탭 구분, # 주석) → {날짜: {키: 값}}.

market-data 레포의 DB를 읽게 되면 같은 모양({날짜: {키: 값}})을 돌려주는 함수를 하나 더 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

_SPLIT = re.compile(r"[,\t ]+")


def read_quotes(paths: str | Path | Iterable[str | Path]) -> dict[date, dict[str, float]]:
    if isinstance(paths, str | Path):
        paths = [paths]
    out: dict[date, dict[str, float]] = {}
    for path in map(Path, paths):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            tokens = _SPLIT.split(line)
            if len(tokens) != 3:
                raise ValueError(f"{path}: '날짜 키 값' 형식이 아니다: {line!r}")
            d, key, value = date.fromisoformat(tokens[0]), tokens[1], float(tokens[2])
            day = out.setdefault(d, {})
            if key in day:
                raise ValueError(f"시세 중복: {d} {key}")
            day[key] = value
    return dict(sorted(out.items()))
