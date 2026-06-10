#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 JLPT 词库 words.json（含 N1 + N2、读音、词性、中文释义、例句、频度、级别）。

数据来自开源 Anki 卡组 “egg rolls JLPT10k”
(https://github.com/5mdld/anki-jlpt-decks) 的 deck-source/notes.csv，
版权归原作者所有。本仓库不二次分发其数据 —— 运行此脚本在本地生成。
"""
import json, os, re, sys, urllib.request

SRC = "https://raw.githubusercontent.com/5mdld/anki-jlpt-decks/HEAD/deck-source/notes.csv"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "words.json")
LEVELS = {"5-N1": "N1", "4-N2": "N2"}   # 想加 N3 就补 "3-N3":"N3"

def strip(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

def main():
    print(f"下载词库源 …\n  {SRC}")
    raw = urllib.request.urlopen(SRC, timeout=30).read().decode("utf-8")

    rows = []
    for line in raw.splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) < 15:
            continue
        deck = c[1]
        level = next((v for k, v in LEVELS.items() if k in deck), None)
        if level is None:
            continue
        word = c[3].strip()
        meaning = strip(c[7])
        if not word or not meaning:
            continue
        m = re.search(r"(高频|中频|低频)", deck)
        rows.append({
            "word": word, "reading": c[6].strip(), "pos": c[5].strip(),
            "meaning": meaning, "example": strip(c[12]), "example_cn": strip(c[14]),
            "freq": m.group(1) if m else "", "level": level,
        })

    seen, uniq = set(), []
    for r in rows:
        k = (r["word"], r["reading"], r["level"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    if not uniq:
        sys.exit("没抽到词条，源格式可能变了。")
    json.dump(uniq, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    n1 = sum(1 for r in uniq if r["level"] == "N1")
    n2 = sum(1 for r in uniq if r["level"] == "N2")
    print(f"✅ 生成 {len(uniq)} 词（N1 {n1} / N2 {n2}）→ {OUT}")


if __name__ == "__main__":
    main()
