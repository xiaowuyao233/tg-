import asyncio, time, json, os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, BotCommand, BotCommandScopeChat
from database import create_local_session, User
from sqlalchemy.future import select
from typing import Callable, Dict, Any, Awaitable, Union
from utils import logger
import messages as msg


class AuthMiddleware(BaseMiddleware):
    """鉴权中间件：检查用户是否被封禁"""

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any]
    ) -> Any:
        uid = event.from_user.id

        session, engine = await create_local_session()
        try:
            u_res = await session.execute(select(User).where(User.user_id == uid))
            user = u_res.scalar_one_or_none()

            if user and user.is_banned:
                if isinstance(event, Message):
                    await event.reply(msg.BANNED_MSG)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg.BANNED_ALERT, show_alert=True)
                return
        finally:
            await session.close()
            await engine.dispose()

        return await handler(event, data)


class BotManager:
    """机器人管理类"""

    def __init__(self, bot_token="", admin_id=0):
        self.bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=None))
        self.dp = Dispatcher()

        self.bot_username = None
        self.admin_id = int(admin_id) if admin_id else 0

        # 用户会话
        self.user_sessions = {}
        self.media_group_buffer = {}
        self.click_cooldown = {}
        self.user_input_state = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = 300

        # 令牌桶限流
        self.token_bucket = 5
        self.token_rate = 0.33
        self.last_token_time = time.time()
        self.global_flood_wait = 0
        self.global_flood_end = 0

        # 用户命令菜单缓存
        self.cmd_menu_cache = {}
        self.cmd_menu_cache_ttl = 300

    async def acquire_token(self):
        """令牌桶算法：获取发送令牌"""
        now = time.time()

        if now < self.global_flood_end:
            wait_time = self.global_flood_end - now
            logger.info(f"⏳ 全局洪水等待中，还需等待 {wait_time:.1f} 秒")
            await asyncio.sleep(wait_time)

        self.token_bucket += (now - self.last_token_time) * self.token_rate
        self.token_bucket = min(self.token_bucket, 10)
        self.last_token_time = now

        if self.token_bucket < 1:
            wait_time = (1 - self.token_bucket) / self.token_rate
            await asyncio.sleep(wait_time)
            self.token_bucket = 0

        self.token_bucket -= 1
        return True

    def set_global_flood_wait(self, wait_seconds):
        """设置全局洪水等待时间"""
        self.global_flood_end = time.time() + wait_seconds
        logger.warning(f"⚠️ 触发洪水保护，需要等待 {wait_seconds} 秒")

    async def start(self):
        """启动机器人"""
        me = await self.bot.get_me()

        if not me.username:
            logger.error("❌ 机器人必须设置用户名才能正常工作！请在 @BotFather 中设置用户名。")
            raise RuntimeError("机器人必须设置用户名")

        self.bot_username = me.username
        logger.info(f"✅ 机器人已启动: @{self.bot_username}")

        # 设置命令菜单
        await self._set_bot_commands()

        # 启动清理任务
        asyncio.create_task(self._cleanup_loop())

    async def _set_bot_commands(self):
        """设置全局默认命令菜单（普通用户看到的）"""
        commands = [
            BotCommand(command="start", description=msg.CMD_DESC_START),
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("✅ 全局命令菜单已设置")
        except Exception as e:
            logger.warning(f"⚠️ 设置命令菜单失败: {e}")

    async def update_user_commands(self, user_id, chat_type="private"):
        """为用户更新专属命令菜单（带缓存）"""
        if chat_type != "private":
            return

        now = time.time()
        cache_key = user_id

        # 缓存未过期则跳过
        if cache_key in self.cmd_menu_cache and now - self.cmd_menu_cache[cache_key] < self.cmd_menu_cache_ttl:
            return

        try:
            if user_id == self.admin_id and self.admin_id:
                # 管理员菜单
                commands = [
                    BotCommand(command="start", description=msg.CMD_DESC_START),
                    BotCommand(command="admin", description=msg.CMD_DESC_ADMIN),
                    BotCommand(command="ban", description=msg.CMD_DESC_BAN),
                    BotCommand(command="unban", description=msg.CMD_DESC_UNBAN),
                    BotCommand(command="check", description=msg.CMD_DESC_CHECK),
                ]
            else:
                # 普通用户菜单
                commands = [
                    BotCommand(command="start", description=msg.CMD_DESC_START),
                ]

            await self.bot.set_my_commands(
                commands,
                scope=BotCommandScopeChat(chat_id=user_id)
            )
            self.cmd_menu_cache[cache_key] = now
        except Exception as e:
            logger.warning(f"⚠️ 设置用户 {user_id} 命令菜单失败: {e}")

    def get_reply_keyboard(self):
        """获取底部键盘"""
        keyboard = [
            [
                types.KeyboardButton(text=msg.BTN_MY_FILES),
                types.KeyboardButton(text=msg.BTN_CONTACT),
                types.KeyboardButton(text=msg.BTN_SPONSOR),
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            selective=False
        )

    def get_config_content(self, text_key, buttons_key, callback_prefix="cfg"):
        """从环境变量获取自定义内容（文本 + 内联按钮）
        支持两种按钮类型：
        - url: 跳转链接 {"text":"...", "url":"..."}
        - copy: 点击复制 {"text":"...", "type":"copy", "copy_text":"..."}
        """
        text = os.getenv(text_key, "")
        text = text.replace("\\n", "\n")
        buttons_json = os.getenv(buttons_key, "[]")

        inline_keyboard = None
        try:
            buttons_data = json.loads(buttons_json)
            if buttons_data:
                rows = []
                for row_data in buttons_data:
                    row = []
                    for btn_data in row_data:
                        btn_type = btn_data.get("type", "url")
                        if btn_type == "copy":
                            copy_text = btn_data.get("copy_text", "")
                            # callback_data 最长 64 字节，截取前 50 字符作为 key
                            callback_data = f"{callback_prefix}:copy:{copy_text[:50]}"
                            row.append(types.InlineKeyboardButton(
                                text=btn_data.get("text", ""),
                                callback_data=callback_data
                            ))
                            # 存储完整的复制文本
                            if not hasattr(self, '_copy_texts'):
                                self._copy_texts = {}
                            self._copy_texts[callback_data] = copy_text
                        else:
                            row.append(types.InlineKeyboardButton(
                                text=btn_data.get("text", ""),
                                url=btn_data.get("url", "")
                            ))
                    rows.append(row)
                if rows:
                    inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=rows)
        except Exception as e:
            logger.error(f"解析按钮配置失败: {e}")

        return text, inline_keyboard

    def get_copy_text(self, callback_data):
        """获取按钮对应的复制文本"""
        if hasattr(self, '_copy_texts') and callback_data in self._copy_texts:
            return self._copy_texts[callback_data]
        return None

    async def _cleanup_loop(self):
        """定期清理过期数据"""
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                if now - self._last_cleanup > self._cleanup_interval:
                    self._cleanup_expired_data(now)
                    self._last_cleanup = now
            except Exception as e:
                logger.error(f"❌ 清理任务执行失败: {e}")

    def _cleanup_expired_data(self, now):
        """清理过期的内存数据"""
        cooldown_ttl = 300
        self.click_cooldown = {k: v for k, v in self.click_cooldown.items() if now - v < cooldown_ttl}

    async def ensure_user(self, user_id, username=None, first_name=None, last_name=None):
        """确保用户存在于数据库中"""
        session, local_engine = await create_local_session()
        try:
            user = (await session.execute(select(User).where(User.user_id == user_id))).scalar_one_or_none()
            if not user:
                user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                session.add(user)
                await session.commit()
                logger.info(f"👤 新用户注册: {user_id}")
            else:
                updated = False
                if username and user.username != username:
                    user.username = username
                    updated = True
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    updated = True
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    updated = True
                user.last_active_at = datetime.now()
                if updated:
                    await session.commit()
        finally:
            await session.close()
            await local_engine.dispose()
