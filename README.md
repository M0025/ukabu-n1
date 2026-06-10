<div align="center">

<img src="assets/banner.png" width="320" alt="ukabu-n1">

# ukabu-n1 · N1 悬浮单词便签

一个常驻桌面的 **JLPT N1 单词悬浮便签**（原生 macOS / AppKit）。
摸鱼时瞄一眼就背词 —— 滚动记忆 + 频度加权 + 「会了」一键淘汰。

</div>

## ✨ 特性

- **无边框毛玻璃便签**，常驻置顶，可拖到任意角落（记住位置）
- **滚动记忆**：面前固定滚动 10 个词，某词出现满 10 遍即「毕业」，自动换入一个新词（一次一个），记得住
- **频度加权**：高频词每轮出现 3 次、中频 2 次、低频 1 次，且更早被引入 —— 把时间花在最该背的词上
- **「✓ 会了」按钮**：点了就标记已掌握、**永不再现**，进度持久保存
- **自动轮播**，可调速；单击换下一个；右键菜单（暂停 / 快慢 / 重置 / 退出）
- 进度（state.json）、位置与速度（config.json）本地保存，关了重开接着学

## 🚀 安装

需要 macOS + Python 3。

```bash
git clone https://github.com/M0025/ukabu-n1.git
cd ukabu-n1

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

python build_data.py        # 本地生成 N1 词库 n1.json
./run.sh                    # 启动
```

> 提示：tkinter 在新版 macOS 上对无边框/透明支持有问题，本项目用原生 **AppKit (PyObjC)** 绘制，因此依赖 `pyobjc-framework-Cocoa`。

### 开机自启（可选）

```bash
bash install/setup-autostart.sh
```

## 🕹 操作

| 操作 | 效果 |
|------|------|
| 拖动 | 移动便签（记住位置）|
| 单击 | 换下一个词 |
| ✓ 会了 | 标记已掌握，永不再现 |
| 右键 | 暂停 / 下一个 / 快一点 / 慢一点 / 重置进度 / 退出 |

## 🙏 致谢 / 数据来源

- 词库数据来自开源 Anki 卡组 **egg rolls JLPT10k**（[5mdld/anki-jlpt-decks](https://github.com/5mdld/anki-jlpt-decks)），版权归原作者。本仓库**不二次分发**其数据，`build_data.py` 在你本地生成 `n1.json`。
- 图标为 AI 生成的原创素材。

## 📄 License

[MIT](LICENSE) © 2026 Misko
