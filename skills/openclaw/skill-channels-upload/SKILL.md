---
name: skill-channels-upload
description: >-
  微信视频号发布：把竖版短视频发布到微信视频号（channels.weixin.qq.com）。当用户说
  "发视频号""上传视频号""视频号发布""发到微信视频号""视频号投稿"时使用。基于通用浏览器
  发布框架（Playwright + 登录态持久化），微信扫码登录。
layer: publish
---

# 微信视频号发布

> 基于通用浏览器发布框架 `../../shared/scripts/web_publisher.py`（`--platform weixin-channels`）。

## ⚠️ 环境依赖

- `pip install playwright` + `playwright install chromium`
- 首次 `login` 用**微信扫码**登录视频号助手，登录态持久化复用
  - 远程/headless 环境用 `login-qr --platform weixin-channels`（抠二维码成图轮询），或走 Web「账号」页登录
- **选择器时效**：视频号发布页描述区可能是富文本 div 而非 textarea，内置选择器为最佳努力，
  **首次务必 `plan` + `--headed` 校验**，失效时更新 `web_publisher.py` 的 weixin-channels 配置。

无浏览器环境可用 `platforms` / `plan` / `check`。

## 执行

```bash
ROOT=<项目根>; WP=$ROOT/skills/shared/scripts/web_publisher.py
python $WP check
python $WP login   --platform weixin-channels           # 微信扫码
python $WP plan    --platform weixin-channels --media out.mp4 --title "标题"
python $WP publish --platform weixin-channels --media out.mp4 --title "标题" --exec --headed
```

## Profile 感知

- 有 Profile：标题短（≤22字）贴合人设；竖版 9:16；可带话题与合集。
- 无 Profile：按视频号通用规范（短标题、竖版、正向内容）。

## 规则

1. 视频号竖版 9:16；横版先 video-reframe 转制。
2. 标题要短（视频号标题偏短），正文可展开。
3. 首次 `--headed` 目视确认扫码与发布流程；选择器失效即更新配置。
4. 视频号内容审核偏严，发布前过 skill-quality-gate 合规检查。

## 参考来源

视频号助手网页发布流程；复用统一 Playwright 框架。微信登录需扫码，选择器按平台现状维护。

## 多画像多账号（画像绑定独立账号）

当会话声明了当前画像（如「我当前使用的画像是『X』」）时，每个画像可绑定**一套独立的平台账号**：
Web「账号」页选中画像 X 后扫码登录，登录态即存入 `~/.easel-browser-profiles/X/`（与通用账号、
其它画像互不影响）。**凡当前画像非空，登录/发布/取数命令必须追加对应画像参数**；画像为空
（通用模式）时按默认路径执行、不带这些参数：

- `web_publisher.py` 全部子命令（login/login-qr/publish/whoami）追加 `--profile-base "$HOME/.easel-browser-profiles/X"`。

当前画像的登录态在 `~/.easel-browser-profiles/X/ChannelsProfile`。
