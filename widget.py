#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JLPT N1 悬浮单词便签 —— 原生 AppKit（无边框 + 毛玻璃）。
· 滚动记忆：WINDOW 个词反复循环，某词满 GRADUATE 遍即毕业换新。
· 频度加权：高频出现多、中频次之、低频最少（引入顺序 + 每轮次数都加权）。
· 「会了」按钮：标记已掌握，永不再现。
拖动移动 · 单击换下一个 · 右键菜单。进度自动保存。
"""
import json, os, random
import build_data
from AppKit import (
    NSApplication, NSApp, NSWindow, NSView, NSTextField, NSButton, NSVisualEffectView,
    NSColor, NSFont, NSMenu, NSMenuItem, NSEvent, NSTimer, NSScreen,
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

DEFAULT_INTERVAL = 20.0
WINDOW = 10
GRADUATE = 10
WIDTH = 300
PAD = 20
BTN_W, BTN_H, GAP = 84, 26, 10
FREQ_W = {"高频": 3.0, "中频": 2.0, "低频": 1.0}   # 频度权重(每轮出现次数)
LEVEL_W = {"N1": 2.0, "N2": 1.0}                  # 级别权重(N1:N2 ≈ 2:1)

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

        tf = NSTextField.alloc().initWithFrame_(NSMakeRect(PAD, PAD, WIDTH, 60))
        tf.setBezeled_(False); tf.setDrawsBackground_(False)
        tf.setEditable_(False); tf.setSelectable_(False); tf.cell().setWraps_(True)
        self.tf = tf; view.addSubview_(tf)

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, BTN_W, BTN_H))
        btn.setTitle_("✓ 会了"); btn.setBezelStyle_(1); btn.setFont_(NSFont.systemFontOfSize_(12))
        btn.setTarget_(self); btn.setAction_("knewIt:")
        self.btn = btn; view.addSubview_(btn)

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

        self.render(); self.startTimer()

    def render(self):
        para = NSMutableParagraphStyle.alloc().init(); para.setLineSpacing_(3.0)
        def seg(t, size, color, bold=False):
            f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
            return NSAttributedString.alloc().initWithString_attributes_(
                t, {NSFontAttributeName: f, NSForegroundColorAttributeName: color,
                    NSParagraphStyleAttributeName: para})
        # 语义自适应色：跟随系统外观，白天=深字、夜间=浅字，两种模式都清晰
        white = NSColor.labelColor()              # 单词(主)
        blue = NSColor.systemTealColor()          # 读音(强调,两模式都可读)
        light = NSColor.labelColor()              # 释义(主)
        foot = NSColor.tertiaryLabelColor()       # 底部信息
        exjp = NSColor.secondaryLabelColor()      # 例句(日)
        excn = NSColor.secondaryLabelColor()      # 例句(中)

        s = NSMutableAttributedString.alloc().init()
        if not self.words:
            s.appendAttributedString_(seg("⚠️ 词库下载失败\n", 20, white, True))
            s.appendAttributedString_(seg("请联网后右键 → 更新词库 重试", 13, foot))
            self.btn.setHidden_(True)
            self.tf.setAttributedStringValue_(s)
            h = self.tf.cell().cellSizeForBounds_(NSMakeRect(0, 0, WIDTH, 10000)).height
            h = float(int(h) + 1); totalW = WIDTH + 2 * PAD
            self.tf.setFrame_(NSMakeRect(PAD, PAD, WIDTH, h))
            newH = h + 2 * PAD
            f = self.win.frame(); top = f.origin.y + f.size.height
            self.win.setFrame_display_(NSMakeRect(f.origin.x, top - newH, totalW, newH), True)
            return
        e = self.roller.current()
        if e is None:
            s.appendAttributedString_(seg("🎉 这批都标记会了！\n", 22, white, True))
            s.appendAttributedString_(seg("右键可重置进度", 13, foot))
            self.btn.setHidden_(True)
        else:
            self.btn.setHidden_(False)
            w = self.words[e["idx"]]
            s.appendAttributedString_(seg(w["word"] + "\n", 30, white, True))
            rd = f"{w.get('reading','')}    {w.get('pos','')}".strip()
            s.appendAttributedString_(seg(rd + "\n", 15, blue))
            s.appendAttributedString_(seg("\n", 5, foot))
            s.appendAttributedString_(seg(w.get("meaning", "") + "\n", 16, light))
            ex, exc = w.get("example", ""), w.get("example_cn", "")
            if ex:
                s.appendAttributedString_(seg("\n", 4, foot))
                s.appendAttributedString_(seg("例  " + ex + "\n", 14, exjp))
                if exc:
                    s.appendAttributedString_(seg("　　" + exc + "\n", 12, excn))
            s.appendAttributedString_(seg("\n", 4, foot))
            lv = w.get("level", "N1"); freq = w.get("freq", "")
            tag = f"{lv} · {freq}" if freq else lv
            s.appendAttributedString_(seg(
                f"{tag}    ·    本词第 {e['seen']+1}/{self.roller.graduate} 遍    ·    已掌握 {len(self.roller.known)}",
                11, foot))

        self.tf.setAttributedStringValue_(s)
        h = self.tf.cell().cellSizeForBounds_(NSMakeRect(0, 0, WIDTH, 10000)).height
        h = float(int(h) + 1)
        totalW = WIDTH + 2 * PAD
        bottom = PAD + (BTN_H + GAP if e is not None else 0)
        self.tf.setFrame_(NSMakeRect(PAD, bottom, WIDTH, h))
        self.btn.setFrame_(NSMakeRect(totalW - PAD - BTN_W, PAD - 2, BTN_W, BTN_H))
        newH = h + bottom + PAD
        f = self.win.frame(); top = f.origin.y + f.size.height
        self.win.setFrame_display_(NSMakeRect(f.origin.x, top - newH, totalW, newH), True)

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

    def popupMenu_(self, event):
        m = NSMenu.alloc().init()
        for title, sel in [("✓ 会了(已掌握)", b"knewIt:"), ("⏸ 暂停 / ▶ 继续", b"togglePause:"),
                           ("下一个", b"nextWord:"), (None, None),
                           ("快一点", b"faster:"), ("慢一点", b"slower:"), (None, None),
                           ("更新词库", b"refreshWords:"), ("重置进度", b"resetProgress:"), ("退出", b"quitApp:")]:
            if title is None: m.addItem_(NSMenuItem.separatorItem()); continue
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
            it.setTarget_(self); m.addItem_(it)
        NSMenu.popUpContextMenu_withEvent_forView_(m, event, self.view)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    ctrl = Controller.alloc().init(); ctrl.setup()
    app.run()

if __name__ == "__main__":
    main()
