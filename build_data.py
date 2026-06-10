#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 JLPT N1 词库 n1.json。

词库数据来自开源 Anki 卡组 “egg rolls JLPT10k”
(https://github.com/5mdld/anki-jlpt-decks) 的 deck-source/notes.csv，
版权归原作者所有。本仓库不二次分发其数据 —— 运行此脚本在本地生成 n1.json。
"""
import json, os, re, sys, urllib.request

SRC = "https://raw.githubusercontent.com/5mdld/anki-jlpt-decks/HEAD/deck-source/notes.csv"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n1.json")


def main():
    print(f"下载词库源 …\n  {SRC}")
    raw = urllib.request.urlopen(SRC, timeout=30).read().decode("utf-8")

    rows = []
    for line in raw.splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) < 8 or "N1" not in c[1]:   # 第 2 列 deck 名含级别
            continue
        word = c[3].strip()
        pos = c[5].strip()
        reading = c[6].strip()
        meaning = re.sub(r"<[^>]+>", "", c[7]).strip()
        if not word or not meaning:
            continue
        m = re.search(r"(高频|中频|低频)", c[1])
        rows.append({"word": word, "reading": reading, "pos": pos,
                     "meaning": meaning, "freq": m.group(1) if m else ""})

    seen, uniq = set(), []
    for r in rows:
        k = (r["word"], r["reading"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    if not uniq:
        sys.exit("没抽到词条，源格式可能变了。")
    json.dump(uniq, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"✅ 生成 {len(uniq)} 个 N1 词条 → {OUT}")


if __name__ == "__main__":
    main()
