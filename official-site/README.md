# 帝三资料库官网

https://dwsg.292828.xyz ：介绍页、安卓安装包下载，以及 App “检查更新”读取的版本通道。
Cloudflare Worker `dwpm-official-site`，静态页面在 `public/`，安装包和版本清单在 R2
存储桶 `dwpm-app-releases`（发布新版不用重新部署网站）。

| 路径 | 内容 |
|---|---|
| `/` | 官网页面（`public/`） |
| `/app/latest.json` | 最新版本清单，App 检查更新读取；`no-cache` + ETag |
| `/app/releases.json` | 全部已发布版本（更新日志） |
| `/download/latest` | 302 到最新版安装包，可长期分享 |
| `/download/dwsg-V<x.y.z>.apk` | 带版本号的正式安装包，支持断点续传，永不覆盖 |

## 发布新版本

```bash
# 1. 构建正式签名包（发布证书在 认证相关/，密码在钥匙串）
cd 自研辅助源码 && JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  node tools/build-production.mjs --keystore ~/Desktop/gitSpaceC/认证相关/dwpm-release.jks

# 2. 发布到官网（先 --dry-run 只检查）
cd official-site && node scripts/publish-release.mjs --note "本次更新内容" --note "另一条说明"
```

发布脚本只接受包名 `com.example.dwpmclone`、非调试、正式证书
（SHA-256 `ad3448dc…627d19`）签名、且版本号大于线上最新版的安装包；按“安装包 →
更新日志 → 最新版本”的顺序上传，手机不会看到指向缺失安装包的版本。

## 开发与部署

```bash
npm install --legacy-peer-deps   # npm 10 在本项目解析 peer 依赖时会崩溃（edgesOut）
npm run check && npm test
npx wrangler deploy              # 需要 CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID
```

`workers.dev` 在国内无法访问，仅用于预览；对外只使用 `dwsg.292828.xyz`。
