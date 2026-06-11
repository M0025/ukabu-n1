#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JLPT N1 悬浮单词便签 —— 原生 AppKit（无边框 + 毛玻璃）。
· 滚动记忆：WINDOW 个词反复循环，某词满 GRADUATE 遍即毕业换新。
· 频度加权：高频出现多、中频次之、低频最少（引入顺序 + 每轮次数都加权）。
· 「会了」按钮：标记已掌握，永不再现。
拖动移动 · 单击换下一个 · 右键菜单。进度自动保存。
"""
import json, os, random, fcntl, threading, subprocess, tempfile, plistlib
import urllib.request, urllib.parse
import objc
import build_data
from _version import __version__
from AppKit import (
    NSApplication, NSApp, NSWindow, NSView, NSTextField, NSButton, NSVisualEffectView,
    NSColor, NSFont, NSMenu, NSMenuItem, NSEvent, NSTimer, NSScreen, NSSound,
    NSStatusBar, NSVariableStatusItemLength, NSAlert,
    NSApplicationActivationPolicyAccessory, NSWindowStyleMaskBorderless,
    NSBackingStoreBuffered, NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary,
    NSVisualEffectBlendingModeBehindWindow, NSVisualEffectStateActive,
    NSFontAttributeName, NSForegroundColorAttributeName, NSParagraphStyleAttributeName,
)
from Foundation import (
    NSObject, NSMakeRect, NSMakePoint,
    NSAttributedString, NSMutableAttributedString, NSMutableParagraphStyle,
)

BASE = os.path.dirname(os.path.abspath(__file__))

# 数据目录：打成 .app 后 bundle 内只读，可写文件须放 Application Support；
# 从源码直接跑（开发 / run.sh）时沿用项目目录，不打扰现有进度。
def _data_dir():
    if ".app/Contents/" in BASE:
        d = os.path.expanduser("~/Library/Application Support/ukabu-n1")
        os.makedirs(d, exist_ok=True)
        return d
    return BASE

DIR = _data_dir()
DATA = os.path.join(DIR, "words.json")    # 词库：首启联网生成（CC BY-NC，详见 README）
CONF = os.path.join(DIR, "config.json")
STATE = os.path.join(DIR, "state.json")
AUDIO_DIR = os.path.join(DIR, "audio")    # 例句/单词 mp3 缓存（按需下载）
MEDIA_URL = "https://raw.githubusercontent.com/5mdld/anki-jlpt-decks/HEAD/deck-source/medias/"
GITHUB_LATEST = "https://api.github.com/repos/M0025/ukabu-n1/releases/latest"

DEFAULT_INTERVAL = 20.0
WINDOW = 10
GRADUATE = 10
WIDTH = 300
PAD = 20
BTN_W, BTN_H, GAP = 84, 26, 10
GAPV = 6                       # 内容块之间竖直间距
EX_BASE, EX_RUBY = 14, 9       # 例句正文 / 假名注音字号
FREQ_W = {"高频": 3.0, "中频": 2.0, "低频": 1.0}   # 频度权重(每轮出现次数)
LEVEL_W = {"N1": 2.0, "N2": 1.0}                  # 级别权重(N1:N2 ≈ 2:1)

_LOCK_FH = None
def single_instance():
    # 排他文件锁，进程存活期间持有；已有实例则返回 False。
    # 防自启(LaunchAgent 直接跑二进制，绕过 LaunchServices 去重) + 手动启动撞出双框。
    global _LOCK_FH
    _LOCK_FH = open(os.path.join(DIR, ".lock"), "w")
    try:
        fcntl.flock(_LOCK_FH, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False

def jload(p, d):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return d

def jsave(p, o):
    try:
        with open(p, "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False)
    except Exception: pass


class Roller:
    def __init__(self, words):
        self.words = words
        self.window_n = WINDOW; self.graduate = GRADUATE
        self.graduated = 0; self.known = set()
        self._load()

    def _freq_w(self, idx):
        return FREQ_W.get(self.words[idx].get("freq", ""), 1.0)

    def _intro_w(self, idx):   # 引入权重 = 级别 × 频度
        return LEVEL_W.get(self.words[idx].get("level", "N1"), 1.0) * self._freq_w(idx)

    def _build_master(self):
        # 加权随机排序(Efraimidis–Spirakis)：权重大→倾向靠前→更早被引入
        keyed = [(random.random() ** (1.0 / self._intro_w(i)), i) for i in range(len(self.words))]
        keyed.sort(reverse=True)
        return [i for _, i in keyed]

    def _in_window(self, idx):
        return any(e["idx"] == idx for e in self.window)

    def _next_new(self):
        while self.cursor < len(self.master):
            idx = self.master[self.cursor]; self.cursor += 1
            if idx in self.known or self._in_window(idx):
                continue
            return {"idx": idx, "seen": 0}
        return None

    def _fresh(self):
        self.master = self._build_master(); self.cursor = 0
        self.window = []; self.graduated = 0
        while len(self.window) < self.window_n:
            e = self._next_new()
            if e is None: break
            self.window.append(e)
        self._new_pass()

    def _load(self):
        s = jload(STATE, None)
        if s and s.get("total") == len(self.words) and s.get("master") and "window" in s:
            self.master = s["master"]; self.cursor = s["cursor"]; self.window = s["window"]
            self.graduated = s.get("graduated", 0); self.known = set(s.get("known", []))
            self.pass_order = s.get("pass_order") or []; self.pass_pos = s.get("pass_pos", 0)
            if not self.window:
                self._fresh()
            elif not self.pass_order or self.pass_pos >= len(self.pass_order):
                self._new_pass()
        else:
            self._fresh()

    def save(self):
        jsave(STATE, {"total": len(self.words), "master": self.master, "cursor": self.cursor,
                      "window": self.window, "graduated": self.graduated,
                      "known": list(self.known),
                      "pass_order": self.pass_order, "pass_pos": self.pass_pos})

    def _new_pass(self):
        # 每轮里高频词出现 3 次、中频 2 次、低频 1 次
        order = []
        for slot, e in enumerate(self.window):
            order += [slot] * int(self._freq_w(e["idx"]))
        random.shuffle(order)
        self.pass_order = order; self.pass_pos = 0

    def current(self):
        if not self.window or not self.pass_order:
            return None
        return self.window[self.pass_order[self.pass_pos]]

    def _replace_slot(self, slot):
        e = self._next_new()
        if e is not None:
            self.window[slot] = e; return False
        self.window.pop(slot); self._new_pass(); return True   # 结构变了

    def advance(self):
        if not self.window or not self.pass_order:
            return
        e = self.current(); e["seen"] += 1
        structural = False
        if e["seen"] >= self.graduate:
            structural = self._replace_slot(self.pass_order[self.pass_pos]); self.graduated += 1
        if not structural:
            self.pass_pos += 1
            if self.pass_pos >= len(self.pass_order): self._new_pass()
        self.save()

    def mark_known(self, idx):
        self.known.add(idx)
        for slot, e in enumerate(list(self.window)):
            if e["idx"] == idx:
                self._replace_slot(slot); break
        self._new_pass(); self.save()


CTRL = None


class RubyView(NSView):
    """手绘注音例句：逐片段画汉字，在汉字正上方画小号假名，按宽度自动换行。
    片段来自 build_data.parse_furigana：[base, reading] 或 [base, reading, 1](目标词)。"""
    def isFlipped(self): return True
    def setSegments_(self, segs):
        self._segs = list(segs or [])
        self.setNeedsDisplay_(True)
    @objc.python_method
    def _fonts(self):
        return (NSFont.systemFontOfSize_(EX_BASE), NSFont.boldSystemFontOfSize_(EX_BASE),
                NSFont.systemFontOfSize_(EX_RUBY))
    @objc.python_method
    def _astr(self, s, f, c=None):
        a = {NSFontAttributeName: f}
        if c is not None: a[NSForegroundColorAttributeName] = c
        return NSAttributedString.alloc().initWithString_attributes_(s, a)
    @objc.python_method
    def _layout(self, width):
        base_f, bold_f, ruby_f = self._fonts()
        rh = self._astr("あ", ruby_f).size().height
        bh = self._astr("あ", base_f).size().height
        line_h = rh + bh
        lines = [[]]; x = 0.0
        for seg in getattr(self, "_segs", []):
            base, reading = seg[0], seg[1]; bold = len(seg) > 2
            bw = self._astr(base, bold_f if bold else base_f).size().width
            if x + bw > width and x > 0:
                lines.append([]); x = 0.0
            lines[-1].append((base, reading, bold, x, bw)); x += bw
        return lines, line_h, rh
    def heightForWidth_(self, width):
        if not getattr(self, "_segs", []): return 0.0
        lines, line_h, _ = self._layout(width)
        return float(len(lines) * line_h)
    def drawRect_(self, rect):
        if not getattr(self, "_segs", []): return
        base_f, bold_f, ruby_f = self._fonts()
        base_c = NSColor.secondaryLabelColor(); bold_c = NSColor.systemTealColor()
        ruby_c = NSColor.tertiaryLabelColor()
        lines, line_h, rh = self._layout(self.frame().size.width)
        y = 0.0
        for line in lines:
            for (base, reading, bold, x, bw) in line:
                self._astr(base, bold_f if bold else base_f, bold_c if bold else base_c)\
                    .drawAtPoint_(NSMakePoint(x, y + rh))
                if reading:
                    r = self._astr(reading, ruby_f, ruby_c); rw = r.size().width
                    r.drawAtPoint_(NSMakePoint(x + (bw - rw) / 2.0, y))
            y += line_h


class DragView(NSView):
    def acceptsFirstMouse_(self, e): return True
    def mouseDown_(self, e):
        self._down = NSEvent.mouseLocation(); self._origin = self.window().frame().origin; self._moved = False
    def mouseDragged_(self, e):
        cur = NSEvent.mouseLocation(); dx = cur.x - self._down.x; dy = cur.y - self._down.y
        if abs(dx) > 2 or abs(dy) > 2: self._moved = True
        self.window().setFrameOrigin_(NSMakePoint(self._origin.x + dx, self._origin.y + dy))
    def mouseUp_(self, e):
        if CTRL is None: return
        if getattr(self, "_moved", False): CTRL.saveOrigin()
        else: CTRL.nextWord_(None)
    def rightMouseDown_(self, e):
        if CTRL: CTRL.popupMenu_(e)


class Controller(NSObject):
    @objc.python_method
    def _play_audio(self, filename):
        # 后台下载(带缓存)，下完回主线程播放。无文件名/失败则静默。
        if not filename: return
        def work():
            path = os.path.join(AUDIO_DIR, filename)
            if not os.path.exists(path):
                try:
                    os.makedirs(AUDIO_DIR, exist_ok=True)
                    data = urllib.request.urlopen(MEDIA_URL + urllib.parse.quote(filename), timeout=8).read()
                    with open(path, "wb") as f: f.write(data)
                except Exception:
                    return
            self.performSelectorOnMainThread_withObject_waitUntilDone_(b"_playFile:", path, False)
        threading.Thread(target=work, daemon=True).start()

    def _playFile_(self, path):
        snd = NSSound.alloc().initWithContentsOfFile_byReference_(path, False)
        if not snd: return
        old = getattr(self, "_snd", None)      # 先停上一个，避免重复点叠音
        if old is not None and old.isPlaying(): old.stop()
        self._snd = snd; snd.play()            # 留引用防止播放中被回收

    def playWord_(self, s): self._play_audio(getattr(self, "_cur_word_audio", ""))
    def playExample_(self, s): self._play_audio(getattr(self, "_cur_ex_audio", ""))

    # ---- 自动更新（查 GitHub Release → 下 universal dmg → 接力脚本换包重启）----
    @objc.python_method
    def _vtuple(self, s):
        out = []
        for p in s.lstrip("vV").split("."):
            n = "".join(ch for ch in p if ch.isdigit())
            out.append(int(n) if n else 0)
        return tuple(out)

    @objc.python_method
    def _check_update(self):
        def work():
            try:
                req = urllib.request.Request(GITHUB_LATEST, headers={
                    "Accept": "application/vnd.github+json", "User-Agent": "ukabu-n1"})
                data = json.loads(urllib.request.urlopen(req, timeout=10).read())
                tag = data.get("tag_name", "")
                if not tag or self._vtuple(tag) <= self._vtuple(__version__):
                    return
                url = ""
                for a in data.get("assets", []):
                    if a.get("name", "").endswith(".dmg"):
                        url = a["browser_download_url"]
                        if "universal" in a["name"]: break
                if not url: return
                self._update = {"version": tag.lstrip("vV"), "url": url}
                self.performSelectorOnMainThread_withObject_waitUntilDone_(b"_onUpdateFound:", None, False)
            except Exception:
                return
        threading.Thread(target=work, daemon=True).start()

    def _onUpdateFound_(self, _):
        self.status.button().setTitle_("語•")     # 红点提示有新版
        self.status.setMenu_(self._menu())

    def doUpdate_(self, s):
        up = getattr(self, "_update", None)
        if not up: return
        al = NSAlert.alloc().init()
        al.setMessageText_(f"更新到 v{up['version']}？")
        al.setInformativeText_("将下载新版、自动替换并重启 ukabu-n1。进度不受影响。")
        al.addButtonWithTitle_("更新"); al.addButtonWithTitle_("取消")
        if al.runModal_() != 1000:                 # NSAlertFirstButtonReturn
            return
        threading.Thread(target=self._do_update, args=(up,), daemon=True).start()

    @objc.python_method
    def _do_update(self, up):
        try:
            app_path = BASE[:BASE.index(".app/") + 4] if ".app/" in BASE else None
            if not app_path: return               # 源码运行不自更新
            tmp = tempfile.mkdtemp(prefix="ukabu-upd-")
            dmg = os.path.join(tmp, "new.dmg")
            urllib.request.urlretrieve(up["url"], dmg)
            pl = plistlib.loads(subprocess.check_output(
                ["hdiutil", "attach", dmg, "-nobrowse", "-plist"]))
            mount = next(e["mount-point"] for e in pl.get("system-entities", []) if e.get("mount-point"))
            staged = os.path.join(tmp, "ukabu-n1.app")
            subprocess.run(["cp", "-R", os.path.join(mount, "ukabu-n1.app"), staged], check=True)
            subprocess.run(["hdiutil", "detach", mount, "-quiet"])
            pid = os.getpid()
            sh = os.path.join(tmp, "swap.sh")
            with open(sh, "w") as f:
                f.write(f'''#!/bin/bash
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
rm -rf "{app_path}" && cp -R "{staged}" "{app_path}"
xattr -dr com.apple.quarantine "{app_path}" 2>/dev/null
open "{app_path}"
rm -rf "{tmp}"
''')
            os.chmod(sh, 0o755)
            subprocess.Popen(["/bin/bash", sh], start_new_session=True)
            self.performSelectorOnMainThread_withObject_waitUntilDone_(b"_quitForUpdate:", None, False)
        except Exception:
            return

    def _quitForUpdate_(self, _):
        NSApp.terminate_(None)

    @objc.python_method
    def _load_words(self, force=False):
        # 首启 / 强制刷新：本地无词库就联网生成。失败返回空，render 提示离线。
        if force:
            try: os.remove(DATA)
            except OSError: pass
        w = jload(DATA, [])
        if not w:
            try:
                build_data.build(DATA); w = jload(DATA, [])
            except Exception:
                w = []
        return w

    def setup(self):
        global CTRL; CTRL = self
        self.words = self._load_words()
        self.conf = jload(CONF, {})
        self.interval = self.conf.get("interval", DEFAULT_INTERVAL)
        self.paused = False
        self.roller = Roller(self.words)

        totalW = WIDTH + 2 * PAD
        rect = NSMakeRect(0, 0, totalW, 140)
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        self.win.setOpaque_(False); self.win.setBackgroundColor_(NSColor.clearColor())
        self.win.setLevel_(NSFloatingWindowLevel); self.win.setHasShadow_(True)
        self.win.setMovableByWindowBackground_(False)
        self.win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary)

        view = DragView.alloc().initWithFrame_(rect)
        view.setWantsLayer_(True); view.layer().setCornerRadius_(16.0); view.layer().setMasksToBounds_(True)
        self.view = view

        fx = NSVisualEffectView.alloc().initWithFrame_(rect)
        fx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        fx.setState_(NSVisualEffectStateActive)
        try: fx.setMaterial_(13)
        except Exception: pass
        fx.setWantsLayer_(True); fx.layer().setCornerRadius_(16.0); fx.layer().setMasksToBounds_(True)
        fx.setAutoresizingMask_(18)
        view.addSubview_(fx)

        def mk_tf():
            t = NSTextField.alloc().initWithFrame_(NSMakeRect(PAD, PAD, WIDTH, 20))
            t.setBezeled_(False); t.setDrawsBackground_(False)
            t.setEditable_(False); t.setSelectable_(False); t.cell().setWraps_(True)
            view.addSubview_(t); return t
        self.tf_top = mk_tf()                    # 单词 + 读音 + 释义
        self.ruby = RubyView.alloc().initWithFrame_(NSMakeRect(PAD, PAD, WIDTH, 20))
        view.addSubview_(self.ruby)              # 例句(注音)
        self.tf_bot = mk_tf()                    # 例句中译 + 底部信息

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, BTN_W, BTN_H))
        btn.setTitle_("✓ 会了"); btn.setBezelStyle_(1); btn.setFont_(NSFont.systemFontOfSize_(12))
        btn.setTarget_(self); btn.setAction_("knewIt:")
        self.btn = btn; view.addSubview_(btn)

        def mk_play(sel):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 22, 22))
            b.setBordered_(False)
            b.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
                "▶", {NSForegroundColorAttributeName: NSColor.systemTealColor(),
                      NSFontAttributeName: NSFont.systemFontOfSize_(12)}))
            b.setTarget_(self); b.setAction_(sel); view.addSubview_(b); return b
        self.play_word = mk_play("playWord:")     # 单词音频(真人)
        self.play_ex = mk_play("playExample:")    # 例句音频(合成)

        self.win.setContentView_(view)

        scr = NSScreen.screens()[0].visibleFrame()
        ww = totalW; wh = self.win.frame().size.height
        x = self.conf.get("x"); y = self.conf.get("y")
        if x is None or y is None:
            x = scr.origin.x + scr.size.width - ww - 30
            y = scr.origin.y + scr.size.height - wh - 30
        x = max(scr.origin.x, min(x, scr.origin.x + scr.size.width - ww))
        y = max(scr.origin.y, min(y, scr.origin.y + scr.size.height - wh))
        self.win.setFrameOrigin_(NSMakePoint(x, y))
        self.win.orderFrontRegardless()

        # 菜单栏图标：藏了也能从这里叫回来（无 Dock 图标，需要常驻控制入口）
        self._hidden = False
        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.status.button().setTitle_("語")
        self.status.button().setToolTip_("ukabu-n1 单词便签")
        self.status.setMenu_(self._menu())

        self.render(); self.startTimer(); self._check_update()

    @objc.python_method
    def _seg(self, t, size, color, bold=False):
        para = NSMutableParagraphStyle.alloc().init(); para.setLineSpacing_(3.0)
        f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        return NSAttributedString.alloc().initWithString_attributes_(
            t, {NSFontAttributeName: f, NSForegroundColorAttributeName: color,
                NSParagraphStyleAttributeName: para})

    @objc.python_method
    def _tf_h(self, tf, astr):
        tf.setAttributedStringValue_(astr)
        return float(int(tf.cell().cellSizeForBounds_(NSMakeRect(0, 0, WIDTH, 10000)).height) + 1)

    def render(self):
        white = NSColor.labelColor(); blue = NSColor.systemTealColor()
        light = NSColor.labelColor(); foot = NSColor.tertiaryLabelColor()
        excn = NSColor.secondaryLabelColor()
        totalW = WIDTH + 2 * PAD

        # 非常规状态：离线 / 全部已掌握 —— 只用 tf_top 顶部一块
        msg = None
        if not self.words:
            msg = self._seg("⚠️ 词库下载失败\n", 20, white, True), self._seg("请联网后右键 → 更新词库 重试", 13, foot)
        else:
            e = self.roller.current()
            if e is None:
                msg = self._seg("🎉 这批都标记会了！\n", 22, white, True), self._seg("右键可重置进度", 13, foot)
        if msg:
            self.btn.setHidden_(True); self.ruby.setHidden_(True); self.tf_bot.setHidden_(True)
            self.play_word.setHidden_(True); self.play_ex.setHidden_(True)
            s = NSMutableAttributedString.alloc().init()
            for part in msg: s.appendAttributedString_(part)
            h = self._tf_h(self.tf_top, s)
            self.tf_top.setHidden_(False)
            newH = h + 2 * PAD
            self.tf_top.setFrame_(NSMakeRect(PAD, PAD, WIDTH, h))
            f = self.win.frame(); top = f.origin.y + f.size.height
            self.win.setFrame_display_(NSMakeRect(f.origin.x, top - newH, totalW, newH), True)
            return

        # 常规：tf_top(词/读音/释义) + ruby(例句注音) + tf_bot(中译 + 底部信息)
        self.btn.setHidden_(False); self.tf_top.setHidden_(False)
        w = self.words[e["idx"]]
        top = NSMutableAttributedString.alloc().init()
        top.appendAttributedString_(self._seg(w["word"] + "\n", 30, white, True))
        rd = f"{w.get('reading','')}    {w.get('pos','')}".strip()
        top.appendAttributedString_(self._seg(rd + "\n", 15, blue))
        top.appendAttributedString_(self._seg("\n", 5, foot))
        top.appendAttributedString_(self._seg(w.get("meaning", ""), 16, light))
        h_top = self._tf_h(self.tf_top, top)

        # 音频文件名(供 ▶ 按钮)
        self._cur_word_audio = w.get("word_audio", "")
        self._cur_ex_audio = w.get("example_audio", "")
        EXIND = 22                              # 例句左缩进，给 ▶ 留位

        ruby_segs = w.get("example_ruby") or []
        has_ex = bool(ruby_segs)
        if has_ex:
            self.ruby.setHidden_(False)
            self.ruby.setSegments_(ruby_segs)   # 「例」前缀由 ▶ 按钮替代
            h_ruby = self.ruby.heightForWidth_(WIDTH - EXIND)
        else:
            self.ruby.setHidden_(True); h_ruby = 0.0

        bot = NSMutableAttributedString.alloc().init()
        exc = w.get("example_cn", "")
        if has_ex and exc:
            bot.appendAttributedString_(self._seg("　　" + exc + "\n", 12, excn))
        bot.appendAttributedString_(self._seg("\n", 4, foot))
        lv = w.get("level", "N1"); freq = w.get("freq", "")
        tag = f"{lv} · {freq}" if freq else lv
        bot.appendAttributedString_(self._seg(
            f"{tag}    ·    本词第 {e['seen']+1}/{self.roller.graduate} 遍    ·    已掌握 {len(self.roller.known)}",
            11, foot))
        h_bot = self._tf_h(self.tf_bot, bot); self.tf_bot.setHidden_(False)

        blocks = [h_top] + ([h_ruby] if has_ex else []) + [h_bot]
        content = sum(blocks) + GAPV * (len(blocks) - 1)
        bottom = PAD + BTN_H + GAP
        newH = bottom + content + PAD

        y = newH - PAD
        y -= h_top; self.tf_top.setFrame_(NSMakeRect(PAD, y, WIDTH, h_top)); y -= GAPV
        if has_ex:
            y -= h_ruby; self.ruby.setFrame_(NSMakeRect(PAD + EXIND, y, WIDTH - EXIND, h_ruby)); ruby_y = y; y -= GAPV
        y -= h_bot; self.tf_bot.setFrame_(NSMakeRect(PAD, y, WIDTH, h_bot))
        self.btn.setFrame_(NSMakeRect(totalW - PAD - BTN_W, PAD - 2, BTN_W, BTN_H))

        # ▶ 单词：词行右上角；▶ 例句：例句首行左侧
        if self._cur_word_audio:
            self.play_word.setHidden_(False)
            self.play_word.setFrame_(NSMakeRect(totalW - PAD - 22, newH - PAD - 30, 22, 22))
        else:
            self.play_word.setHidden_(True)
        if has_ex and self._cur_ex_audio:
            self.play_ex.setHidden_(False)
            self.play_ex.setFrame_(NSMakeRect(PAD - 2, ruby_y + h_ruby - 31, 22, 22))
        else:
            self.play_ex.setHidden_(True)

        f = self.win.frame(); wtop = f.origin.y + f.size.height
        self.win.setFrame_display_(NSMakeRect(f.origin.x, wtop - newH, totalW, newH), True)

    def startTimer(self):
        if getattr(self, "timer", None): self.timer.invalidate()
        if not self.paused:
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                self.interval, self, b"tick:", None, True)

    def tick_(self, t): self.roller.advance(); self.render()
    def nextWord_(self, s): self.roller.advance(); self.render(); self.startTimer()
    def knewIt_(self, s):
        e = self.roller.current()
        if e is not None: self.roller.mark_known(e["idx"])
        self.render(); self.startTimer()
    def togglePause_(self, s): self.paused = not self.paused; self.startTimer()
    def faster_(self, s):
        self.interval = max(3.0, self.interval - 3); self.conf["interval"] = self.interval
        jsave(CONF, self.conf); self.startTimer()
    def slower_(self, s):
        self.interval += 3; self.conf["interval"] = self.interval; jsave(CONF, self.conf); self.startTimer()
    def resetProgress_(self, s): self.roller._fresh(); self.roller.save(); self.render(); self.startTimer()
    def refreshWords_(self, s):
        self.words = self._load_words(force=True)
        self.roller = Roller(self.words)   # 词条变动会按 total 不符自动重置进度
        self.render(); self.startTimer()
    def quitApp_(self, s): NSApp.terminate_(None)
    def saveOrigin(self):
        o = self.win.frame().origin
        self.conf["x"] = float(o.x); self.conf["y"] = float(o.y); jsave(CONF, self.conf)

    @objc.python_method
    def _menu(self):
        m = NSMenu.alloc().init()
        up = getattr(self, "_update", None)
        if up:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"🟢 更新到 v{up['version']}", b"doUpdate:", "")
            it.setTarget_(self); m.addItem_(it); m.addItem_(NSMenuItem.separatorItem())
        toggle = "显示便签" if getattr(self, "_hidden", False) else "隐藏便签"
        for title, sel in [(toggle, b"toggleHidden:"), (None, None),
                           ("✓ 会了(已掌握)", b"knewIt:"), ("⏸ 暂停 / ▶ 继续", b"togglePause:"),
                           ("下一个", b"nextWord:"), (None, None),
                           ("快一点", b"faster:"), ("慢一点", b"slower:"), (None, None),
                           ("更新词库", b"refreshWords:"), ("重置进度", b"resetProgress:"), (None, None),
                           ("退出", b"quitApp:")]:
            if title is None: m.addItem_(NSMenuItem.separatorItem()); continue
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
            it.setTarget_(self); m.addItem_(it)
        return m

    def toggleHidden_(self, s):
        self._hidden = not getattr(self, "_hidden", False)
        if self._hidden: self.win.orderOut_(None)
        else: self.win.orderFrontRegardless()
        self.status.setMenu_(self._menu())     # 刷新菜单里的「显示/隐藏」字样

    def popupMenu_(self, event):
        NSMenu.popUpContextMenu_withEvent_forView_(self._menu(), event, self.view)


def main():
    if not single_instance():
        return                      # 已有一个在跑，静默退出
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    ctrl = Controller.alloc().init(); ctrl.setup()
    app.run()

if __name__ == "__main__":
    main()
