#!/usr/bin/env python3
"""data/ 以下の TSV を検査し、IME 用の辞書ファイルを生成する。

    python3 tools/build.py          # 検査して dist/ を生成
    python3 tools/build.py --check  # 検査のみ（エラーがあれば終了コード 1）

data/terms/ と data/names/ が本体の辞書になり、data/extra/ の各ファイルは
それぞれ別の追加辞書になる。
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DIST = ROOT / "dist"

POS = ("名詞", "さ変名詞", "形容動詞", "人名")
MAX_LEN = 60  # MS IME の読み・語句の上限
READING_RE = re.compile(r"[ぁ-ゖー]+")


def load(path):
    """TSV を読み、(よみ, 表記, 品詞, 場所) の列とエラーの列を返す。"""
    entries, errors = [], []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        where = f"{path.relative_to(ROOT)}:{lineno}"
        cols = raw.split("\t")
        if len(cols) not in (3, 4):
            errors.append(f"{where}: 列数が {len(cols)}（3 か 4 のはず）: {raw!r}")
            continue
        reading, word, pos = cols[0], cols[1], cols[2]
        if not READING_RE.fullmatch(reading):
            errors.append(f"{where}: 読みにひらがな以外の文字: {reading!r}")
        if not word or word != word.strip():
            errors.append(f"{where}: 表記が空か前後に空白: {word!r}")
        if pos not in POS:
            errors.append(f"{where}: 未知の品詞: {pos!r}")
        if len(reading) > MAX_LEN or len(word) > MAX_LEN:
            errors.append(f"{where}: {MAX_LEN} 文字を超えている")
        entries.append((reading, word, pos, where))
    return entries, errors


def merge(entries):
    """同じ（よみ, 表記）を 1 つにまとめ、(語の列, 警告の列) を返す。

    品詞が食い違うときは、名詞より さ変名詞・形容動詞 を採る（「〜する」「〜な」でも
    変換できるように）。さ変名詞と形容動詞が食い違うときは先のものを採って警告する。
    """
    chosen, warnings = {}, []
    for reading, word, pos, where in entries:
        key = (reading, word)
        if key not in chosen:
            chosen[key] = (pos, where)
            continue
        prev_pos, prev_where = chosen[key]
        if pos == prev_pos or pos == "名詞":
            continue
        if prev_pos == "名詞":
            chosen[key] = (pos, where)
            continue
        warnings.append(
            f"{where}: {reading} {word} の品詞 {pos} が {prev_where} の {prev_pos} と食い違う（先を採用）"
        )
    return [(r, w, pos) for (r, w), (pos, _) in chosen.items()], warnings


def dictionaries():
    """(名前, 元ファイルの列) を、本体の辞書、追加辞書の順に返す。"""
    yield "", sorted((DATA / "terms").glob("*.tsv")) + sorted((DATA / "names").glob("*.tsv"))
    for f in sorted((DATA / "extra").glob("*.tsv")):
        yield f.stem, [f]


def with_katakana_vu(entries):
    """読みに ゔ を含む語について、ヴ 読みの行を追加する。

    Windows 10 (2020) 以前の Microsoft IME はひらがな入力中の vu を ヴ にするため、
    どちらの IME でも引けるよう両方を登録する。
    """
    out = []
    for reading, word, pos in entries:
        out.append((reading, word, pos))
        if "ゔ" in reading:
            out.append((reading.replace("ゔ", "ヴ"), word, pos))
    return out


def write_ms_ime(entries, name, path):
    """Microsoft IME のユーザー辞書ツールが読み込めるテキスト（UTF-16LE, BOM 付き, CRLF）。"""
    lines = [
        "!Microsoft IME Dictionary Tool",
        "!Format:WORDLIST",
        f"!User Dictionary Name: {name}",
        "",
    ]
    lines += [f"{r}\t{w}\t{p}" for r, w, p in with_katakana_vu(entries)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-16-le", newline="\r\n") as f:
        f.write("﻿" + "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="検査のみ行い、ファイルを生成しない")
    ap.add_argument(
        "--pos-simple",
        action="store_true",
        help="品詞をすべて 名詞 にして生成する（IME が品詞名を受け付けないとき用）",
    )
    args = ap.parse_args()

    built, failed, in_main = [], False, set()
    for extra, files in dictionaries():
        entries, errors = [], []
        for f in files:
            e, err = load(f)
            entries += e
            errors += err
        for e in errors:
            print("エラー:", e, file=sys.stderr)
        failed |= bool(errors)

        merged, warnings = merge(entries)
        for w in warnings:
            print("警告:", w, file=sys.stderr)
        if extra:
            # 本体にもある語は追加辞書に入れない
            merged = [e for e in merged if e[:2] not in in_main]
        else:
            in_main = {e[:2] for e in merged}

        name = "math-dic-jp" + (f"-{extra}" if extra else "")
        print(f"{name}: {len(files)} ファイル, {len(merged)} 語")
        built.append((extra, name, merged))

    if failed:
        return 1
    if args.check:
        return 0

    for extra, name, merged in built:
        if args.pos_simple:
            merged = [(r, w, "名詞") for r, w, _ in merged]
        out = DIST / "windows" / ("math-dic-ms-ime" + (f"-{extra}" if extra else "") + ".txt")
        write_ms_ime(merged, name, out)
        print(f"生成: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
