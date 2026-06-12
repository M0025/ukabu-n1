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
# 英文释义（JMdict/EDRDG, CC BY-SA）：开发时由 JMdict 预生成的小映射「词\t读音→英文」
_GLOSS_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glosses_en.json")
_GLOSS_URL = "https://raw.githubusercontent.com/M0025/ukabu-n1/main/glosses_en.json"

def load_glosses(timeout=30):
    try:
        if os.path.exists(_GLOSS_LOCAL):
            return json.load(open(_GLOSS_LOCAL, encoding="utf-8"))
    except Exception: pass
    try:
        return json.loads(urllib.request.urlopen(_GLOSS_URL, timeout=timeout).read())
    except Exception:
        return {}

def strip(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

_TOK = re.compile(r"([^\s\[\]\x01\x02]+)(?:\[([^\]]+)\])?")
def parse_furigana(raw):
    """把 Anki 注音格式 `<b>漢字[よみ]</b> 初期[しょき]の` 解析成片段列表。
    每个片段 [base, reading]，目标词(原 <b>)再加一个 1 → [base, reading, 1]。
    纯假名/标点 reading 为 ""。空输入返回 []。"""
    if not raw:
        return []
    s = raw.replace("<b>", "\x01").replace("</b>", "\x02")
    s = re.sub(r"<[^>]+>", "", s)
    segs, bold, pos = [], False, 0
    while pos < len(s):
        ch = s[pos]
        if ch == "\x01": bold = True; pos += 1; continue
        if ch == "\x02": bold = False; pos += 1; continue
        if ch.isspace(): pos += 1; continue
        m = _TOK.match(s, pos)
        if not m or not m.group(1):
            pos += 1; continue
        seg = [m.group(1), m.group(2) or ""]
        if bold: seg.append(1)
        segs.append(seg); pos = m.end()
    return segs

def snd(c, i):
    """从 `[sound:文件名.mp3]` 列抽出文件名；越界/无音频返回 ""。"""
    if i >= len(c): return ""
    m = re.search(r"\[sound:(.+?)\]", c[i])
    return m.group(1) if m else ""

def build(out_path=OUT, timeout=30):
    """下载并解析上游 CSV，写出词库 JSON 到 out_path，返回词条列表。
    可被 widget.py 在首启 / 「更新词库」时导入调用。失败抛异常。"""
    raw = urllib.request.urlopen(SRC, timeout=timeout).read().decode("utf-8")

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
        ruby = parse_furigana(c[13])
        if not ruby and c[12].strip():        # c[13] 缺注音时退回纯例句
            ruby = [[strip(c[12]), ""]]
        rows.append({
            "word": word, "reading": c[6].strip(), "pos": c[5].strip(),
            "meaning": meaning, "example_ruby": ruby, "example_cn": strip(c[14]),
            "word_audio": snd(c, 10), "example_audio": snd(c, 16),
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
        raise RuntimeError("没抽到词条，源格式可能变了。")
    gl = load_glosses(timeout)                  # 贴英文释义（缺则空，widget 端回退中文）
    for r in uniq:
        r["meaning_en"] = gl.get(f'{r["word"]}\t{r["reading"]}', "")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(uniq, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return uniq

def main():
    print(f"下载词库源 …\n  {SRC}")
    try:
        uniq = build(OUT)
    except Exception as e:
        sys.exit(str(e))
    n1 = sum(1 for r in uniq if r["level"] == "N1")
    n2 = sum(1 for r in uniq if r["level"] == "N2")
    print(f"✅ 生成 {len(uniq)} 词（N1 {n1} / N2 {n2}）→ {OUT}")


if __name__ == "__main__":
    main()
