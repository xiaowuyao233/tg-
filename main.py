import asyncio
import os
import traceback

from database import init_db
from core_bot import BotManager, AuthMiddleware
from handlers import register_handlers
from utils import logger

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def main():
    """主函数"""
    print("=" * 50)
    print("  🤖 Telegram 文件分享机器人")
    print("  📦 极简版 (单机器人 + SQLite + aiogram)")
    print("=" * 50)
    print()

    print(">>> 正在初始化数据库...")
    await init_db()
    print(">>> 数据库初始化完成")

    # 从环境变量读取配置
    bot_token = os.getenv("BOT_TOKEN", "")
    admin_id_str = os.getenv("ADMIN_ID", "0")

    print()
    print(">>> 配置检查:")
    print(f"    Bot Token: {'已配置' if bot_token else '❌ 未配置'}")
    print(f"    Admin ID: {admin_id_str if admin_id_str != '0' else '未配置'}")
    print()

    if not bot_token:
        print(">>> ⚠️  缺少必要配置！")
        print(">>> ")
        print(">>> 请在 .env 文件中配置以下变量：")
        print(">>>   BOT_TOKEN - 机器人 Token")
        print(">>>   ADMIN_ID - 管理员用户 ID (可选)")
        print(">>> ")
        print(">>> 获取 Bot Token: https://t.me/BotFather")
        print(">>> ")
        return

    try:
        admin_id = int(admin_id_str) if admin_id_str else 0
    except ValueError:
        print(">>> ❌ Admin ID 格式错误，请输入数字")
        return

    print(">>> 正在启动机器人...")

    try:
        bot_mgr = BotManager(
            bot_token=bot_token,
            admin_id=admin_id
        )

        # 注册中间件
        bot_mgr.dp.message.middleware(AuthMiddleware())
        bot_mgr.dp.callback_query.middleware(AuthMiddleware())

        # 注册处理器
        register_handlers(bot_mgr)

        # 启动机器人
        await bot_mgr.start()

        print()
        print(">>> ✅ 机器人启动成功！")
        print(f">>> 🤖 用户名: @{bot_mgr.bot_username}")
        if admin_id:
            print(f">>> 👑 管理员 ID: {admin_id}")
        print(">>> ")
        print(">>> 按 Ctrl+C 停止")
        print(">>> ")

        # 开始轮询
        await bot_mgr.dp.start_polling(bot_mgr.bot)

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
        print(">>> 正在停止机器人...")
        try:
            await bot_mgr.dp.stop_polling()
            await bot_mgr.bot.session.close()
        except Exception:
            pass
        print(">>> 机器人已停止")
    except Exception as e:
        logger.error(f"机器人启动失败: {e}")
        traceback.print_exc()
        print(f">>> ❌ 机器人启动失败: {e}")


if __name__ == "__main__":
    try:
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n>>> 服务已退出")
