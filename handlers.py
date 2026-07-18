import asyncio, time, re
from datetime import datetime
from aiogram import F, types
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    Message, CallbackQuery, InputMediaPhoto, InputMediaVideo,
    InputMediaDocument, InputMediaAudio, InputMediaAnimation,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from database import create_local_session, FileCode, FileRecord, SystemConfig, User
from sqlalchemy.future import select
from sqlalchemy import desc, func
from core_bot import BotManager
from utils import generate_xl_code, logger
import messages as msg


async def _get_page_config():
    """获取翻页配置"""
    session, engine = await create_local_session()
    try:
        res = await session.execute(select(SystemConfig))
        configs = {c.key: c.value for c in res.scalars().all()}
        return {
            "page_cooldown": int(configs.get("page_cooldown", "3")),
            "msgs_per_page": int(configs.get("msgs_per_page", "1")),
        }
    finally:
        await session.close()
        await engine.dispose()


async def _count_files(db_ids):
    """统计文件数量"""
    if not db_ids:
        return 0, 0, 0, 0, 0

    session, engine = await create_local_session()
    try:
        f_ids = list(dict.fromkeys(db_ids))
        res = await session.execute(select(FileRecord).where(FileRecord.id.in_(f_ids)))
        files = res.scalars().all()
        p = len([f for f in files if f.file_type == 'photo'])
        v = len([f for f in files if f.file_type == 'video'])
        d = len([f for f in files if f.file_type == 'document'])
        a = len([f for f in files if f.file_type == 'audio'])
        other = len(files) - p - v - d - a
        return len(files), p, v, d, a + other
    finally:
        await session.close()
        await engine.dispose()


def _build_media_input(f, file_id):
    """构建媒体输入对象"""
    caption = f.caption or ""
    if f.file_type == 'photo':
        return InputMediaPhoto(media=file_id, caption=caption)
    elif f.file_type == 'video':
        return InputMediaVideo(media=file_id, caption=caption)
    elif f.file_type == 'document':
        return InputMediaDocument(media=file_id, caption=caption)
    elif f.file_type == 'audio':
        return InputMediaAudio(media=file_id, caption=caption)
    elif f.file_type == 'animation':
        return InputMediaAnimation(media=file_id, caption=caption)
    return None


async def _send_page_media(bot_mgr: BotManager, uid, files):
    """发送页面媒体文件（带限流保护）"""
    media_group = []
    for f in files:
        if f.file_id:
            media_obj = _build_media_input(f, f.file_id)
            if media_obj:
                media_group.append(media_obj)

    if not media_group:
        return

    await bot_mgr.acquire_token()

    try:
        if len(media_group) == 1:
            m_obj = media_group[0]
            if isinstance(m_obj, InputMediaPhoto):
                await bot_mgr.bot.send_photo(uid, m_obj.media, caption=m_obj.caption)
            elif isinstance(m_obj, InputMediaVideo):
                await bot_mgr.bot.send_video(uid, m_obj.media, caption=m_obj.caption)
            elif isinstance(m_obj, InputMediaDocument):
                await bot_mgr.bot.send_document(uid, m_obj.media, caption=m_obj.caption)
            elif isinstance(m_obj, InputMediaAudio):
                await bot_mgr.bot.send_audio(uid, m_obj.media, caption=m_obj.caption)
            elif isinstance(m_obj, InputMediaAnimation):
                await bot_mgr.bot.send_animation(uid, m_obj.media, caption=m_obj.caption)
        else:
            await bot_mgr.bot.send_media_group(uid, media=media_group)
    except TelegramRetryAfter as e:
        bot_mgr.set_global_flood_wait(e.retry_after)
        await asyncio.sleep(e.retry_after)
        await _send_page_media(bot_mgr, uid, files)
    except Exception as e:
        logger.error(f"发送媒体失败: {e}")


def _build_page_nav(code, page, total_pages):
    """构建翻页按钮"""
    btns = []
    row = []

    for i in range(1, total_pages + 1):
        if i == page:
            btn_text = f"🔘 {i}"
        else:
            btn_text = str(i)
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"p:{code}:{i}"))
        if len(row) == 5:
            btns.append(row)
            row = []

    if row:
        btns.append(row)

    if total_pages > 1:
        jump_btn = InlineKeyboardButton(text=msg.BTN_JUMP, callback_data=f"jump:{code}")
        btns.append([jump_btn])

    return InlineKeyboardMarkup(inline_keyboard=btns) if btns else None


async def send_page_logic(bot_mgr: BotManager, uid, code, page, is_first_extract=False):
    """发送指定页的文件内容"""

    session, engine = await create_local_session()
    try:
        fc = (await session.execute(select(FileCode).where(FileCode.code == code))).scalar_one_or_none()
        if not fc:
            await bot_mgr.bot.send_message(uid, msg.INVALID_CODE)
            return

        if is_first_extract:
            fc.hits += 1

        f_ids = [fid for fid in fc.file_ids.split(",") if fid]
        if not f_ids:
            await bot_mgr.bot.send_message(uid, msg.NO_FILES)
            return

        res_files = await session.execute(select(FileRecord).where(FileRecord.id.in_(f_ids)))
        files_map = {f.id: f for f in res_files.scalars().all()}
        ordered_files = [files_map[int(fid)] for fid in f_ids if int(fid) in files_map]

        # 按媒体组逻辑分块（图片/视频10个一组）
        logical_msgs = []
        chunk = []
        for f in ordered_files:
            if f.file_type in ['photo', 'video']:
                chunk.append(f)
                if len(chunk) == 10:
                    logical_msgs.append(chunk)
                    chunk = []
            else:
                if chunk:
                    logical_msgs.append(chunk)
                    chunk = []
                logical_msgs.append([f])
        if chunk:
            logical_msgs.append(chunk)

        page_config = await _get_page_config()
        msgs_per_page = page_config["msgs_per_page"]

        total_pages = max(1, (len(logical_msgs) + msgs_per_page - 1) // msgs_per_page)
        page = max(1, min(page, total_pages))

        current_page_msgs = logical_msgs[(page - 1) * msgs_per_page: page * msgs_per_page]

        # 发送媒体
        for msg_chunk in current_page_msgs:
            await _send_page_media(bot_mgr, uid, msg_chunk)

        # 统计信息
        p = len([f for f in ordered_files if f.file_type == 'photo'])
        v = len([f for f in ordered_files if f.file_type == 'video'])
        d = len([f for f in ordered_files if f.file_type == 'document'])

        text = msg.PAGE_INFO.format(
            page=page, total=total_pages, count=len(ordered_files),
            p=p, v=v, d=d
        )

        if fc.note:
            text += msg.PAGE_NOTE.format(note=fc.note)

        nav_markup = _build_page_nav(code, page, total_pages)

        await bot_mgr.bot.send_message(uid, text, reply_markup=nav_markup, disable_web_page_preview=True)

        await session.commit()
    finally:
        await session.close()
        await engine.dispose()


async def wait_for_group(bot_mgr: BotManager, uid, gid):
    """等待媒体组接收完成，然后更新状态消息"""
    await asyncio.sleep(1.2)
    if gid in bot_mgr.media_group_buffer:
        bot_mgr.media_group_buffer.pop(gid, None)
        await update_upload_status(bot_mgr, uid)


async def update_upload_status(bot_mgr: BotManager, uid):
    """更新上传状态消息（删除旧的，发新的，带防抖）"""
    sess = bot_mgr.user_sessions.get(uid)
    if not sess:
        return

    # 防抖：记录最后一次请求时间
    now = time.time()
    sess["_last_status_req"] = now
    # 等 1 秒看有没有新的请求
    await asyncio.sleep(1)
    # 如果又有新的请求，这次就跳过
    if sess.get("_last_status_req") != now:
        return

    total, p, v, d, other = await _count_files(sess.get("db_ids", []))

    text = msg.UPLOAD_STATUS_TEXT.format(total=total)
    if p or v or d or other:
        parts = []
        if p:
            parts.append(f"🖼️ {p}")
        if v:
            parts.append(f"📹 {v}")
        if d:
            parts.append(f"📄 {d}")
        if other:
            parts.append(f"📁 {other}")
        text += "  ".join(parts) + "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=msg.BTN_CANCEL, callback_data="upload_cancel"),
            InlineKeyboardButton(text=msg.BTN_FINISH, callback_data="upload_finish"),
        ]
    ])

    # 删除旧的状态消息
    old_msg_id = sess.get("status_msg_id")
    if old_msg_id:
        try:
            await bot_mgr.bot.delete_message(uid, old_msg_id)
        except Exception:
            pass

    # 发送新的状态消息
    try:
        status_msg = await bot_mgr.bot.send_message(uid, text, reply_markup=keyboard)
        sess["status_msg_id"] = status_msg.message_id
    except Exception:
        pass


async def finalize_upload(bot_mgr: BotManager, uid, note=None):
    """结束上传，生成文件码"""
    sess = bot_mgr.user_sessions.pop(uid, None)
    if not sess:
        return

    db_ids = sess.get("db_ids", [])
    if not db_ids:
        return

    # 生成文件码
    prefix = bot_mgr.bot_username if bot_mgr.bot_username else "FILEBOT"
    total, p, v, d, other = await _count_files(db_ids)
    code = generate_xl_code(p, v, d, other, prefix=prefix)

    # 如果没有传备注，尝试从第一个文件自动获取
    if not note:
        session, engine = await create_local_session()
        try:
            f_ids = list(dict.fromkeys(db_ids))
            if f_ids:
                res = await session.execute(select(FileRecord).where(FileRecord.id == int(f_ids[0])))
                first_file = res.scalar_one_or_none()
                if first_file:
                    if first_file.caption and first_file.caption.strip():
                        note = first_file.caption.strip()[:50]
                    elif first_file.file_name:
                        note = first_file.file_name[:50]
        finally:
            await session.close()
            await engine.dispose()

    # 保存文件码
    session, engine = await create_local_session()
    try:
        file_ids_str = ",".join(map(str, list(dict.fromkeys(db_ids))))
        fc = FileCode(code=code, creator_id=uid, file_ids=file_ids_str, note=note)
        session.add(fc)
        await session.commit()
        logger.info(f"✅ 文件码已生成: {code}, 创建者: {uid}, 文件数: {total}")
    finally:
        await session.close()
        await engine.dispose()

    # 发送结果（关闭 Markdown 解析，避免用户输入的备注导致解析错误）
    decoder_text = f"@{bot_mgr.bot_username}" if bot_mgr.bot_username else "本机器人"
    text = msg.UPLOAD_SUCCESS_TITLE + "\n"
    text += msg.UPLOAD_SUCCESS_CODE.format(code=code) + "\n"
    text += msg.UPLOAD_SUCCESS_BOT.format(bot=decoder_text) + "\n"
    if note:
        text += msg.UPLOAD_SUCCESS_NOTE.format(note=note) + "\n"

    # 尝试使用 copy_text 原生复制（需 aiogram 3.13+），否则回退到 callback_data
    try:
        from aiogram.types import CopyTextButton
        copy_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=msg.UPLOAD_COPY_BTN, copy_text=CopyTextButton(text=text))]
        ])
    except ImportError:
        copy_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=msg.UPLOAD_COPY_BTN, callback_data=f"copy:{code}")]
        ])

    # 文件码用 Markdown 发送（需要 code 块格式），结果用纯文本发送
    await bot_mgr.bot.send_message(uid, text, reply_markup=copy_btn, parse_mode=None)

    # 温馨提示
    await bot_mgr.bot.send_message(uid, msg.UPLOAD_TIP, parse_mode=None)

    return code


async def admin_ban_user(bot_mgr: BotManager, admin_id, target_uid):
    """封禁用户"""
    if admin_id != bot_mgr.admin_id or not bot_mgr.admin_id:
        return msg.ADMIN_ONLY

    session, engine = await create_local_session()
    try:
        user = (await session.execute(select(User).where(User.user_id == target_uid))).scalar_one_or_none()
        if not user:
            return msg.ADMIN_USER_NOT_FOUND
        user.is_banned = True
        await session.commit()
        logger.warning(f"👑 管理员 {admin_id} 封禁用户 {target_uid}")
        return msg.ADMIN_BAN_SUCCESS.format(uid=target_uid)
    finally:
        await session.close()
        await engine.dispose()


async def admin_unban_user(bot_mgr: BotManager, admin_id, target_uid):
    """解封用户"""
    if admin_id != bot_mgr.admin_id or not bot_mgr.admin_id:
        return msg.ADMIN_ONLY

    session, engine = await create_local_session()
    try:
        user = (await session.execute(select(User).where(User.user_id == target_uid))).scalar_one_or_none()
        if not user:
            return msg.ADMIN_USER_NOT_FOUND
        user.is_banned = False
        await session.commit()
        logger.info(f"👑 管理员 {admin_id} 解封用户 {target_uid}")
        return msg.ADMIN_UNBAN_SUCCESS.format(uid=target_uid)
    finally:
        await session.close()
        await engine.dispose()


async def admin_check_user(bot_mgr: BotManager, admin_id, target_uid):
    """查看用户信息"""
    if admin_id != bot_mgr.admin_id or not bot_mgr.admin_id:
        return msg.ADMIN_ONLY

    session, engine = await create_local_session()
    try:
        user = (await session.execute(select(User).where(User.user_id == target_uid))).scalar_one_or_none()
        if not user:
            return msg.ADMIN_USER_NOT_FOUND
        status = msg.ADMIN_STATUS_BANNED if user.is_banned else msg.ADMIN_STATUS_NORMAL
        return msg.ADMIN_CHECK_INFO.format(
            uid=user.user_id,
            username=user.username or "无",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            status=status,
            created_at=user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else "未知",
            last_active=user.last_active_at.strftime('%Y-%m-%d %H:%M') if user.last_active_at else "未知"
        )
    finally:
        await session.close()
        await engine.dispose()


async def send_user_list(bot_mgr: BotManager, uid, page=1):
    """发送用户的文件列表"""
    session, engine = await create_local_session()
    try:
        count_res = await session.execute(
            select(func.count(FileCode.code)).where(FileCode.creator_id == uid)
        )
        total_count = count_res.scalar() or 0

        if not total_count:
            await bot_mgr.bot.send_message(uid, msg.MY_FILES_EMPTY)
            return

        total_pages = (total_count + 9) // 10
        page = max(1, min(page, total_pages))
        offset = (page - 1) * 10

        codes = (await session.execute(
            select(FileCode)
            .where(FileCode.creator_id == uid)
            .order_by(desc(FileCode.created_at))
            .offset(offset).limit(10)
        )).scalars().all()

        text = msg.MY_FILES_TITLE.format(page=page, total=total_pages)

        for i, fc in enumerate(codes, 1):
            f_count = len([fid for fid in fc.file_ids.split(",") if fid])
            text += msg.MY_FILES_ITEM.format(
                idx=i + offset, code=fc.code, count=f_count, hits=fc.hits
            )
            if fc.note:
                text += msg.MY_FILES_NOTE.format(note=fc.note)
            text += msg.MY_FILES_DATE.format(date=fc.created_at.strftime('%Y-%m-%d %H:%M'))

        await bot_mgr.bot.send_message(uid, text)
    finally:
        await session.close()
        await engine.dispose()


def register_handlers(bot_mgr: BotManager):
    """注册所有消息处理器"""
    dp = bot_mgr.dp

    @dp.message(F.text & F.chat.type == "private")
    async def h_text_handler(message: Message, bot_mgr=bot_mgr):
        """文本消息处理（按优先级：输入状态 > 底部按钮 > 文件码）"""
        uid = message.from_user.id
        text = message.text.strip()

        # 更新用户命令菜单
        try:
            await bot_mgr.update_user_commands(uid, message.chat.type)
        except Exception as e:
            logger.warning(f"⚠️ 更新命令菜单失败: {e}")

        # 1. 输入状态处理（优先级最高）
        if uid in bot_mgr.user_input_state:
            state = bot_mgr.user_input_state.get(uid)
            val = text

            if state["type"] == "upload_note":
                if len(val) > 50:
                    await message.reply(msg.NOTE_TOO_LONG)
                    return

                # 删除备注提示消息
                note_msg_id = state.get("note_msg_id")
                if note_msg_id:
                    try:
                        await bot_mgr.bot.delete_message(uid, note_msg_id)
                    except Exception:
                        pass

                bot_mgr.user_input_state.pop(uid, None)
                await finalize_upload(bot_mgr, uid, note=val)
                return

            if state["type"] == "jump":
                bot_mgr.user_input_state.pop(uid, None)
                if not val.isdigit():
                    await message.reply(msg.INVALID_PAGE)
                    return
                await send_page_logic(bot_mgr, uid, state["code"], int(val), is_first_extract=False)
                return

        # 2. 底部按钮处理
        if text == msg.BTN_MY_FILES:
            await send_user_list(bot_mgr, uid, page=1)
            return

        if text == msg.BTN_CONTACT:
            contact_text, contact_kb = bot_mgr.get_config_content("CONTACT_TEXT", "CONTACT_BUTTONS", "contact")
            if contact_text:
                await message.reply(contact_text, reply_markup=contact_kb, disable_web_page_preview=True)
            return

        if text == msg.BTN_SPONSOR:
            sponsor_text, sponsor_kb = bot_mgr.get_config_content("SPONSOR_TEXT", "SPONSOR_BUTTONS", "sponsor")
            if sponsor_text:
                await message.reply(sponsor_text, reply_markup=sponsor_kb, disable_web_page_preview=True)
            return

        # 3. 管理员命令
        if text == "/admin":
            if uid == bot_mgr.admin_id and bot_mgr.admin_id:
                await message.reply(msg.ADMIN_PANEL_TITLE + "\n\n" + msg.ADMIN_CMD_LIST)
            else:
                await message.reply(msg.ADMIN_ONLY)
            return

        if text.startswith("/ban "):
            parts = text.split()
            if len(parts) < 2:
                await message.reply(msg.ADMIN_USAGE_BAN)
                return
            target_id_str = parts[1]
            if not target_id_str.isdigit():
                await message.reply(msg.ADMIN_INVALID_ID)
                return
            result = await admin_ban_user(bot_mgr, uid, int(target_id_str))
            await message.reply(result)
            return

        if text.startswith("/unban "):
            parts = text.split()
            if len(parts) < 2:
                await message.reply(msg.ADMIN_USAGE_UNBAN)
                return
            target_id_str = parts[1]
            if not target_id_str.isdigit():
                await message.reply(msg.ADMIN_INVALID_ID)
                return
            result = await admin_unban_user(bot_mgr, uid, int(target_id_str))
            await message.reply(result)
            return

        if text.startswith("/check "):
            parts = text.split()
            if len(parts) < 2:
                await message.reply(msg.ADMIN_USAGE_CHECK)
                return
            target_id_str = parts[1]
            if not target_id_str.isdigit():
                await message.reply(msg.ADMIN_INVALID_ID)
                return
            result = await admin_check_user(bot_mgr, uid, int(target_id_str))
            await message.reply(result)
            return

        # 4. 命令处理
        if text.startswith("/start"):
            parts = text.split()
            if len(parts) > 1:
                code = parts[1]
                await send_page_logic(bot_mgr, uid, code, page=1, is_first_extract=True)
                return

            await message.reply(msg.WELCOME_TEXT, reply_markup=bot_mgr.get_reply_keyboard())
            return

        # 5. 如果正在上传中，文本消息不尝试解码（避免误触发）
        if uid in bot_mgr.user_sessions:
            return

        # 6. 尝试解码文件码（支持整条消息提取）
        # 先用正则从消息中提取文件码（格式：前缀_xxx_随机10位）
        code_match = re.search(r'[A-Za-z0-9_]{4,}_[A-Za-z0-9]*[PVDO][A-Za-z0-9]*_[A-Za-z0-9]{10}', text)
        extract_code = code_match.group(0) if code_match else None

        # 如果没匹配到但文本长度合适，直接用整段文本尝试
        if not extract_code and 4 <= len(text) <= 100 and ' ' not in text.strip():
            extract_code = text.strip()

        if extract_code:
            session, engine = await create_local_session()
            try:
                fc = (await session.execute(select(FileCode).where(FileCode.code == extract_code))).scalar_one_or_none()
                if fc:
                    await send_page_logic(bot_mgr, uid, extract_code, page=1, is_first_extract=True)
                    return
            finally:
                await session.close()
                await engine.dispose()

    @dp.message(F.chat.type == "private", F.photo | F.video | F.document | F.audio | F.animation)
    async def h_media_handler(message: Message, bot_mgr=bot_mgr):
        """处理媒体文件上传"""
        uid = message.from_user.id

        # 更新用户命令菜单
        try:
            await bot_mgr.update_user_commands(uid, message.chat.type)
        except Exception as e:
            logger.warning(f"⚠️ 更新命令菜单失败: {e}")

        # 确保用户存在
        try:
            await bot_mgr.ensure_user(
                uid,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
        except Exception as e:
            logger.error(f"❌ ensure_user 失败: {e}")

        # 如果处于备注输入状态，忽略媒体
        if uid in bot_mgr.user_input_state and bot_mgr.user_input_state[uid].get("type") == "upload_note":
            return

        # 自动创建上传会话
        if uid not in bot_mgr.user_sessions:
            bot_mgr.user_sessions[uid] = {
                "last_active": datetime.now(),
                "db_ids": [],
                "status_msg_id": None,
            }

        bot_mgr.user_sessions[uid]["last_active"] = datetime.now()

        # 处理媒体文件
        try:
            # 确定文件类型和对象
            file_type = None
            media_obj = None

            if message.photo:
                file_type = 'photo'
                media_obj = message.photo[-1]
            elif message.video:
                file_type = 'video'
                media_obj = message.video
            elif message.document:
                file_type = 'document'
                media_obj = message.document
            elif message.audio:
                file_type = 'audio'
                media_obj = message.audio
            elif message.animation:
                file_type = 'animation'
                media_obj = message.animation

            if not file_type or not media_obj:
                return

            file_id = media_obj.file_id
            file_unique_id = media_obj.file_unique_id
            file_name = getattr(media_obj, "file_name", None)

            if not file_id or not file_unique_id:
                logger.error("文件缺少必要信息")
                return

            # 检查文件是否已存在
            session, engine = await create_local_session()
            try:
                existing_file = (await session.execute(
                    select(FileRecord).where(FileRecord.file_unique_id == file_unique_id)
                )).scalar_one_or_none()

                if existing_file:
                    file_record_id = existing_file.id
                    if existing_file.file_id != file_id:
                        existing_file.file_id = file_id
                        await session.commit()
                else:
                    caption = message.caption
                    db_f = FileRecord(
                        file_unique_id=file_unique_id,
                        file_id=file_id,
                        file_type=file_type,
                        file_name=file_name,
                        caption=caption,
                        media_group_id=message.media_group_id
                    )
                    session.add(db_f)
                    await session.commit()
                    file_record_id = db_f.id
                    logger.info(f"📥 新文件保存成功: ID={file_record_id}, 类型={file_type}")
            finally:
                await session.close()
                await engine.dispose()

            # 添加到用户会话
            if file_record_id not in bot_mgr.user_sessions[uid]["db_ids"]:
                bot_mgr.user_sessions[uid]["db_ids"].append(file_record_id)

            # 更新状态（防抖机制自动合并多次调用）
            await update_upload_status(bot_mgr, uid)

        except Exception as e:
            logger.error(f"处理媒体文件失败: {e}")

    # =============== 回调按钮处理 ===============

    @dp.callback_query(F.data == "upload_cancel")
    async def h_upload_cancel(query: CallbackQuery, bot_mgr=bot_mgr):
        """取消上传"""
        await query.answer()
        uid = query.from_user.id

        if uid in bot_mgr.user_sessions:
            sess = bot_mgr.user_sessions.pop(uid)
            # 删除状态消息
            status_msg_id = sess.get("status_msg_id")
            if status_msg_id:
                try:
                    await bot_mgr.bot.delete_message(uid, status_msg_id)
                except Exception:
                    pass

        await bot_mgr.bot.send_message(uid, msg.UPLOAD_CANCELED)

    @dp.callback_query(F.data == "upload_finish")
    async def h_upload_finish(query: CallbackQuery, bot_mgr=bot_mgr):
        """结束上传，弹备注输入"""
        await query.answer()
        uid = query.from_user.id

        sess = bot_mgr.user_sessions.get(uid)
        if not sess or not sess.get("db_ids"):
            await bot_mgr.bot.send_message(uid, msg.UPLOAD_NO_FILES)
            return

        # 删除状态消息
        status_msg_id = sess.get("status_msg_id")
        if status_msg_id:
            try:
                await bot_mgr.bot.delete_message(uid, status_msg_id)
            except Exception:
                pass

        # 发送备注提示
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=msg.BTN_CANCEL, callback_data="upload_note_cancel")]
        ])

        note_msg = await bot_mgr.bot.send_message(
            uid,
            msg.UPLOAD_NOTE_PROMPT,
            reply_markup=keyboard
        )

        bot_mgr.user_input_state[uid] = {
            "type": "upload_note",
            "note_msg_id": note_msg.message_id,
        }

    @dp.callback_query(F.data == "upload_note_cancel")
    async def h_upload_note_cancel(query: CallbackQuery, bot_mgr=bot_mgr):
        """取消备注输入，直接生成文件码（不带备注）"""
        await query.answer()
        uid = query.from_user.id

        # 删除备注提示消息
        try:
            await bot_mgr.bot.delete_message(uid, query.message.message_id)
        except Exception:
            pass

        # 清除输入状态
        if uid in bot_mgr.user_input_state:
            bot_mgr.user_input_state.pop(uid, None)

        # 直接生成文件码（不带备注）
        await finalize_upload(bot_mgr, uid, note=None)

    @dp.callback_query(F.data.startswith("copy:"))
    async def h_copy(query: CallbackQuery, bot_mgr=bot_mgr):
        """复制文件码（低版本回退：toast 提示，密钥已在消息中可复制）"""
        code = query.data.split(":", 1)[1]
        await query.answer(f"📋 {code}")

    @dp.callback_query(F.data.startswith("contact:copy:") | F.data.startswith("sponsor:copy:"))
    async def h_cfg_copy(query: CallbackQuery, bot_mgr=bot_mgr):
        """配置按钮的点击复制（低版本回退：toast 提示）"""
        copy_text = bot_mgr.get_copy_text(query.data)
        if copy_text:
            await query.answer(f"📋 {copy_text}")
        else:
            await query.answer()

    @dp.callback_query(F.data.startswith("p:"))
    async def h_page_nav(query: CallbackQuery, bot_mgr=bot_mgr):
        """翻页回调"""
        await query.answer()
        parts = query.data.split(":")
        if len(parts) < 3:
            return

        code = parts[1]
        try:
            page = int(parts[2])
        except ValueError:
            return

        uid = query.from_user.id

        # 冷却检查
        now = time.time()
        cooldown_key = f"{uid}_{code}"
        if cooldown_key in bot_mgr.click_cooldown:
            last_click = bot_mgr.click_cooldown[cooldown_key]
            page_config = await _get_page_config()
            if now - last_click < page_config["page_cooldown"]:
                remaining = int(page_config["page_cooldown"] - (now - last_click))
                await query.answer(msg.COOLDOWN_MSG.format(sec=remaining), show_alert=True)
                return

        bot_mgr.click_cooldown[cooldown_key] = now

        await send_page_logic(bot_mgr, uid, code, page, is_first_extract=False)

    @dp.callback_query(F.data.startswith("jump:"))
    async def h_jump(query: CallbackQuery, bot_mgr=bot_mgr):
        """跳转页码回调"""
        await query.answer()
        code = query.data.split(":", 1)[1]
        uid = query.from_user.id
        bot_mgr.user_input_state[uid] = {"type": "jump", "code": code}
        await bot_mgr.bot.send_message(uid, msg.JUMP_PROMPT)
