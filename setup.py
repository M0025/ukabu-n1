#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""py2app 打包配置 —— 生成 ukabu-n1.app。

    pip install py2app
    python setup.py py2app          # 产物在 dist/ukabu-n1.app

词库不打进包：app 首启联网生成到 ~/Library/Application Support/ukabu-n1/
（数据 CC BY-NC，见 README）。build_data 模块需随包带上以供首启 / 更新词库调用。
"""
from setuptools import setup

APP = ["widget.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "includes": ["build_data"],
    "iconfile": "assets/icon.icns",
    "plist": {
        "CFBundleName": "ukabu-n1",
        "CFBundleDisplayName": "ukabu-n1",
        "CFBundleIdentifier": "com.ukabu.n1",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,          # 纯悬浮挂件，无 Dock 图标（与 Accessory 策略一致）
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "MIT © 2026 Misko · 词库 CC BY-NC 4.0 (5mdld/anki-jlpt-decks)",
    },
}

setup(
    app=APP,
    name="ukabu-n1",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
