# 喵喵治愈屋 · 高贵白猫优化版

这是适合 Render 部署的 Flask 网页小游戏版本。

## 本版优化

- 手机端主界面尽量控制在一屏内，主要状态直接显示在顶部。
- 状态、商店、日记、设置改为手机底部多窗口入口，不需要一直上下滑动。
- 喂食、摸摸、玩耍、洗澡、睡觉、拍照都有独立动画反馈。
- 小猫从猫头升级为完整的高贵白猫形象，包含身体、尾巴、爪子、皇冠和饰品。
- 保留等级、成就、日记、商店、导入导出存档和 PWA 添加到桌面功能。

## Render 设置

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```
