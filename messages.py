"""
回复文本配置
所有机器人回复的文本都集中在这里，方便修改
"""

# ============= 欢迎与帮助 =============
WELCOME_TEXT = (
    "👋 欢迎使用文件分享机器人！\n\n"
    "📤 上传文件：直接发送图片/视频/文档即可\n"
    "   （发送文件后点击「结束添加」生成文件码）\n\n"
    "📥 解码文件：发送文件码即可查看\n"
)

# ============= 上传相关 =============
UPLOAD_STATUS_TEXT = "📦 是否结束添加文件呢？\n继续发送就可以接着添加哦～\n已收到文件 {total} 个 ✨\n"
UPLOAD_NOTE_PROMPT = "✏️ 请给这批文件写个备注吧～"
UPLOAD_CANCELED = "❌ 已取消上传"
UPLOAD_NO_FILES = "⚠️ 没有文件可以生成"
NOTE_TOO_LONG = "⚠️ 备注不能超过50字，请重新输入。"

# ============= 上传成功 =============
UPLOAD_SUCCESS_TITLE = "🎉 存储成功啦！"
UPLOAD_SUCCESS_CODE = "🔑 文件密钥: {code}"
UPLOAD_SUCCESS_BOT = "🤖 解码机器人: {bot}"
UPLOAD_SUCCESS_NOTE = "📝 备注: {note}"
UPLOAD_COPY_BTN = "📋 点击复制密钥信息"

UPLOAD_TIP = (
    "⚠️ 温馨提示～\n"
    "本机器人不会备份文件本体\n"
    "请妥善保存密钥，别弄丢啦！🙏"
)

# ============= 解码相关 =============
INVALID_CODE = "❌ 文件码无效或已过期"
NO_FILES = "❌ 该文件码没有文件"
PAGE_INFO = "📊 第 {page}/{total} 页  |  文件总数：{count}\n🖼️ 图片: {p}  📹 视频: {v}  📄 文档: {d}"
PAGE_NOTE = "\n📝 备注: {note}"
JUMP_PROMPT = "🔢 请输入要跳转的页码："
INVALID_PAGE = "⚠️ 请输入有效的页码数字。"
COOLDOWN_MSG = "⏳ 请稍候 {sec} 秒"

# ============= 我的文件 =============
MY_FILES_TITLE = "📁 我的文件 (第 {page}/{total} 页)\n\n"
MY_FILES_EMPTY = "📭 您还没有上传任何文件"
MY_FILES_ITEM = "{idx}. {code}\n   📦 {count} 个文件 | 👁️ {hits} 次提取\n"
MY_FILES_NOTE = "   📝 {note}\n"
MY_FILES_DATE = "   📅 {date}\n\n"

# ============= 封禁 =============
BANNED_MSG = "🚫 您已被封禁，无法使用本机器人。"
BANNED_ALERT = "🚫 您已被封禁"

# ============= 底部按钮 =============
BTN_MY_FILES = "📁 我的"
BTN_CONTACT = "📢 防失联"
BTN_SPONSOR = "💖 赞助"

# ============= 内联按钮 =============
BTN_CANCEL = "❌ 取消"
BTN_FINISH = "✅ 结束添加"
BTN_JUMP = "🔢 跳转到第...页"

# ============= 管理员相关 =============
ADMIN_ONLY = "⚠️ 只有管理员可以使用此命令"
ADMIN_USAGE_BAN = "ℹ️ 用法：/ban 用户ID\n例如：/ban 123456789"
ADMIN_USAGE_UNBAN = "ℹ️ 用法：/unban 用户ID\n例如：/unban 123456789"
ADMIN_USAGE_CHECK = "ℹ️ 用法：/check 用户ID\n例如：/check 123456789"
ADMIN_INVALID_ID = "⚠️ 请输入有效的用户ID（数字）"
ADMIN_BAN_SUCCESS = "✅ 已封禁用户 `{uid}`"
ADMIN_UNBAN_SUCCESS = "✅ 已解封用户 `{uid}`"
ADMIN_USER_NOT_FOUND = "⚠️ 未找到该用户"
ADMIN_CHECK_INFO = (
    "👤 用户信息：\n"
    "• ID: `{uid}`\n"
    "• 用户名: @{username}\n"
    "• 昵称: {first_name} {last_name}\n"
    "• 状态: {status}\n"
    "• 注册时间: {created_at}\n"
    "• 最后活跃: {last_active}"
)
ADMIN_STATUS_BANNED = "🚫 已封禁"
ADMIN_STATUS_NORMAL = "✅ 正常"

ADMIN_PANEL_TITLE = "👑 管理员面板"
ADMIN_CMD_LIST = (
    "📋 管理命令列表：\n\n"
    "/ban 用户ID - 封禁用户\n"
    "/unban 用户ID - 解封用户\n"
    "/check 用户ID - 查看用户信息\n"
)

# 命令菜单描述
CMD_DESC_START = "开始使用"
CMD_DESC_BAN = "封禁用户"
CMD_DESC_UNBAN = "解封用户"
CMD_DESC_CHECK = "查看用户信息"
CMD_DESC_ADMIN = "管理员面板"
