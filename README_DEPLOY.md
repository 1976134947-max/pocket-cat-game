# 喵喵治愈屋：公网部署版

这个版本适合部署到 Render、Railway、Fly.io、PythonAnywhere 等 Python Web 平台。

## 本地运行

```bash
pip install -r requirements.txt
python app.py
```

## Render 部署

1. 把本文件夹上传到 GitHub 仓库。
2. 登录 Render，New → Web Service。
3. 选择这个 GitHub 仓库。
4. Build Command 填：

```bash
pip install -r requirements.txt
```

5. Start Command 填：

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

部署完成后，Render 会给你一个公网网址，手机直接用浏览器打开即可。

## 注意

免费云平台可能会休眠，第一次打开会慢一点。未配置持久化磁盘时，云服务重启后 cat_save.json 可能丢失。
