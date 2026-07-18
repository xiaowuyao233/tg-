# 🤖 Telegram 文件解码器机器人
tg:@xiashang1

文件解码/分享机器人，基于 aiogram 3 + SQLite。

## ✨ 功能特性

- 📤 **文件上传**：直接发送图片/视频/文档，批量上传生成文件码
- 📥 **文件解码**：发送文件码即可提取文件
- 📁 **我的文件**：底部键盘查看上传记录
- 🔒 **封禁管理**：管理员可封禁/解封用户
- 📢 **防失联 & 赞助**：自定义内容，支持内联按钮
- ⚡ **令牌桶限流**：避免触发 Telegram 洪水限制
- 💾 **SQLite 数据库**：无需额外配置数据库

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制 `.env` 并填写配置：

```env
BOT_TOKEN=你的机器人Token
ADMIN_ID=你的用户ID

# 防失联配置（换行用 \n 表示）
CONTACT_TEXT=📢 防失联\n\n关注我们，永不迷路！
CONTACT_BUTTONS=[[{"text":"📢 点击关注","url":"https://t.me/your_channel"}]]

# 赞助配置（换行用 \n 表示）
SPONSOR_TEXT=💖 支持我们\n\n如果这个机器人对你有帮助，欢迎赞助支持！
SPONSOR_BUTTONS=[[{"text":"💖 点击赞助","url":"https://your-sponsor-link.com"}]]
```

### 3. 启动

```bash
python main.py
```

## 📖 使用说明

### 普通用户

| 操作 | 说明 |
|------|------|
| 直接发送文件 | 开始上传，支持图片/视频/文档/音频/动图 |
| 点击「结束添加」 | 填写备注后生成文件码 |
| 发送文件码 | 提取文件内容 |
| 📁 我的 | 查看自己上传的文件列表 |
| 📢 防失联 | 查看联系方式 |
| 💖 赞助 | 赞助支持 |

### 管理员

| 命令 | 说明 | 用法 |
|------|------|------|
| `/admin` | 管理员面板，查看所有命令 | `/admin` |
| `/ban` | 封禁用户 | `/ban 123456789` |
| `/unban` | 解封用户 | `/unban 123456789` |
| `/check` | 查看用户信息 | `/check 123456789` |

> 💡 管理员命令菜单会自动显示，普通用户只看到 `/start`

## 📁 项目结构

```
.
├── main.py          # 程序入口
├── core_bot.py      # 机器人核心（BotManager + 中间件）
├── handlers.py      # 消息处理器
├── database.py      # 数据库模型与操作
├── messages.py      # 回复文本配置
├── utils.py         # 工具函数
├── requirements.txt # Python 依赖
└── .env             # 环境配置
```

## 🗄️ 数据库

数据库文件路径：`./data/bot.db`（自动创建）

### 数据表

- `users` - 用户表
- `files` - 文件记录表
- `file_codes` - 文件码表
- `system_config` - 系统配置表

## ⚙️ 技术栈

- **框架**：aiogram 3.x
- **数据库**：SQLite + SQLAlchemy (async)
- **限流**：令牌桶算法
- **配置**：dotenv + 环境变量

## 📝 配置说明

### 必填配置

| 变量 | 说明 |
|------|------|
| `BOT_TOKEN` | 机器人 Token，从 [@BotFather](https://t.me/BotFather) 获取 |
| `ADMIN_ID` | 管理员用户 ID（可选，建议配置） |

### 自定义配置

| 变量 | 说明 |
|------|------|
| `CONTACT_TEXT` | 防失联文本内容，`\n` 表示换行 |
| `CONTACT_BUTTONS` | 防失联内联按钮，JSON 格式 |
| `SPONSOR_TEXT` | 赞助文本内容，`\n` 表示换行 |
| `SPONSOR_BUTTONS` | 赞助内联按钮，JSON 格式 |

按钮格式示例：
```json
[
  [{"text":"按钮1","url":"https://example.com"}],
  [{"text":"按钮2","url":"https://example2.com"}]
]
```

## 🛡️ 安全说明

- API Key 等敏感信息存放在 `.env` 文件中
- `.env` 文件不要提交到 Git
- 数据库文件存放于 `./data/` 目录，建议定期备份

## 📄 License

MIT
