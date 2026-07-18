import random, string, logging, os
from logging.handlers import TimedRotatingFileHandler

def generate_xl_code(p, v, d, o, prefix="XLDZZZ2"):
    # 格式：前缀_3P5V_随机10位
    stats = ""
    if p: stats += f"{p}P"
    if v: stats += f"{v}V"
    if d: stats += f"{d}D"
    if o: stats += f"{o}O"
    
    checksum = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"{prefix}_{stats}_{checksum}"

# 日志配置
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("XL_Bot")
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler("logs/bot.log", when="midnight", backupCount=14, encoding="utf-8")
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
console = logging.StreamHandler()
console.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logger.addHandler(console)