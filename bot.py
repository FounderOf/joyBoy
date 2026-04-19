"""
JoyCannot Discord Bot
Author: JoyCannot Team
Version: 1.3.0
License: MIT

Changes v1.3.0:
  - Payment methods now support real account details (QRIS URL/info, Bank rekening, E-Wallet number)
  - Premium command lock system: lock any command as 💎 PREMIUM via interactive UI
  - Premium label auto-applied to slash command descriptions after lock/unlock (re-sync)
  - Prefix users get embed notification when trying a premium-locked command
  - All owner/setup commands now use embed + button UI (maintenance, setchannel)
  - Maintenance broadcast: compose → preview → confirm flow with Edit/Cancel buttons
  - setchannel: modal-based input with server list view
  - Premium is per-user ID only (no per-server role exploit)
  - Guild premium nickname: owner activates 'JoyCannot Premium' nickname per server
  - Nickname auto-restored on bot restart for all activated guilds
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import datetime
import re
import pytz
import logging
from collections import defaultdict
from typing import Optional

logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

EMBED_COLOR = 0xD97706   # Dark orange
BOT_PREFIX  = "!Joy "
CONFIG_PATH = "data/config.json"
WIB         = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────
# CONFIG MANAGER
# ─────────────────────────────────────────────

def load_config() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        default = {
            "guilds": {},
            "premium_packages": [],
            "premium_commands": [],
            "premium_users":    [],
            "premium_guilds":   [],
            "avatar_default":   "",   # URL of normal bot avatar
            "avatar_premium":   "",   # URL of premium bot avatar
            "vote_discount":    10,
            "topgg_webhook_secret": "",
            "votes": {},
            "payment_methods": {
                "qris":    {"enabled": True, "image_url": "", "info": ""},
                "bank":    {"enabled": True, "bank_name": "", "account_number": "", "account_name": ""},
                "ewallet": {"enabled": True, "type": "", "number": ""},
            }
        }
        save_config(default)
        return default
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # ── Migrate old boolean payment_methods → new dict format ──
    pm = data.get("payment_methods", {})
    if pm and isinstance(next(iter(pm.values()), None), bool):
        data["payment_methods"] = {
            "qris":    {"enabled": pm.get("qris",    True), "image_url": "", "info": ""},
            "bank":    {"enabled": pm.get("bank",    True), "bank_name": "", "account_number": "", "account_name": ""},
            "ewallet": {"enabled": pm.get("ewallet", True), "type": "", "number": ""},
        }
    if "payment_methods" not in data:
        data["payment_methods"] = {
            "qris":    {"enabled": True, "image_url": "", "info": ""},
            "bank":    {"enabled": True, "bank_name": "", "account_number": "", "account_name": ""},
            "ewallet": {"enabled": True, "type": "", "number": ""},
        }
    data.setdefault("premium_commands", [])
    data.setdefault("premium_users",    [])
    data.setdefault("premium_guilds",   [])
    data.setdefault("avatar_default",   "")
    data.setdefault("avatar_premium",   "")
    data.setdefault("vote_discount",    10)
    data.setdefault("topgg_webhook_secret", "")
    data.setdefault("votes",            {})
    # ── Migrate whitelist_role → support_role in all guilds ──────────────
    for gid, gc in data.get("guilds", {}).items():
        tkt = gc.get("ticket", {})
        if "whitelist_role" in tkt and "support_role" not in tkt:
            tkt["support_role"] = tkt.pop("whitelist_role")
    save_config(data)
    return data

def save_config(cfg: dict):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def guild_cfg(cfg: dict, guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in cfg["guilds"]:
        cfg["guilds"][gid] = {
            "language": "en",
            "main_channel": None,
            "announce_channel": None,
            "ticket": {
                "category": None,
                "log_channel": None,
                "support_role": None,   # role that can see & handle tickets
                "max_tickets": 1,       # max open tickets per user
                "panels": []
            },
            "warnings": {},
            "active_tickets": {}
        }
        save_config(cfg)
    gc = cfg["guilds"][gid]
    # Migrate whitelist_role → support_role if needed
    tkt = gc.get("ticket", {})
    if "whitelist_role" in tkt and "support_role" not in tkt:
        tkt["support_role"] = tkt.pop("whitelist_role")
    tkt.setdefault("max_tickets", 1)
    return gc

# ─────────────────────────────────────────────
# LANGUAGE SYSTEM
# ─────────────────────────────────────────────

LANGUAGES = {
    "en": "English", "id": "Indonesian", "de": "German",
    "ar": "Arabic",  "th": "Thai",       "vi": "Vietnamese",
    "ja": "Japanese","ko": "Korean",
}

STRINGS = {
    "en": {
        "no_perm":         "❌ You do not have permission to use this command.",
        "kick_success":    "✅ {user} has been kicked. Reason: {reason}",
        "ban_success":     "✅ {user} has been banned. Reason: {reason}",
        "timeout_success": "✅ {user} has been timed out for {duration} minutes.",
        "warn_success":    "⚠️ {user} has been warned. Reason: {reason}",
        "role_add":        "✅ Role {role} added to {user}.",
        "role_remove":     "✅ Role {role} removed from {user}.",
        "move_success":    "✅ {user} moved to {channel}.",
        "emoji_add":       "✅ Emoji {name} added.",
        "ticket_open":     "🎫 Your ticket has been created: {channel}",
        "ticket_exists":   "❌ You already have an open ticket.",
        "lang_set":        "✅ Language set to {lang}.",
        "antispam_ban":    "🔨 {user} was banned for cross-channel spam.",
    },
    "id": {
        "no_perm":         "❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.",
        "kick_success":    "✅ {user} telah dikick. Alasan: {reason}",
        "ban_success":     "✅ {user} telah diban. Alasan: {reason}",
        "timeout_success": "✅ {user} telah di-timeout selama {duration} menit.",
        "warn_success":    "⚠️ {user} telah diperingatkan. Alasan: {reason}",
        "role_add":        "✅ Peran {role} ditambahkan ke {user}.",
        "role_remove":     "✅ Peran {role} dihapus dari {user}.",
        "move_success":    "✅ {user} dipindahkan ke {channel}.",
        "emoji_add":       "✅ Emoji {name} berhasil ditambahkan.",
        "ticket_open":     "🎫 Tiket kamu telah dibuat: {channel}",
        "ticket_exists":   "❌ Kamu sudah memiliki tiket yang terbuka.",
        "lang_set":        "✅ Bahasa diatur ke {lang}.",
        "antispam_ban":    "🔨 {user} diban karena spam lintas saluran.",
    },
    "de": {
        "no_perm":         "❌ Du hast keine Berechtigung, diesen Befehl zu verwenden.",
        "kick_success":    "✅ {user} wurde gekickt. Grund: {reason}",
        "ban_success":     "✅ {user} wurde gebannt. Grund: {reason}",
        "timeout_success": "✅ {user} wurde für {duration} Minuten stummgeschaltet.",
        "warn_success":    "⚠️ {user} wurde verwarnt. Grund: {reason}",
        "role_add":        "✅ Rolle {role} zu {user} hinzugefügt.",
        "role_remove":     "✅ Rolle {role} von {user} entfernt.",
        "move_success":    "✅ {user} wurde nach {channel} verschoben.",
        "emoji_add":       "✅ Emoji {name} hinzugefügt.",
        "ticket_open":     "🎫 Dein Ticket wurde erstellt: {channel}",
        "ticket_exists":   "❌ Du hast bereits ein offenes Ticket.",
        "lang_set":        "✅ Sprache auf {lang} gesetzt.",
        "antispam_ban":    "🔨 {user} wurde wegen kanalübergreifendem Spam gebannt.",
    },
    "ar": {
        "no_perm":         "❌ ليس لديك صلاحية استخدام هذا الأمر.",
        "kick_success":    "✅ تم طرد {user}. السبب: {reason}",
        "ban_success":     "✅ تم حظر {user}. السبب: {reason}",
        "timeout_success": "✅ تم إسكات {user} لمدة {duration} دقيقة.",
        "warn_success":    "⚠️ تم تحذير {user}. السبب: {reason}",
        "role_add":        "✅ تمت إضافة دور {role} إلى {user}.",
        "role_remove":     "✅ تمت إزالة دور {role} من {user}.",
        "move_success":    "✅ تم نقل {user} إلى {channel}.",
        "emoji_add":       "✅ تمت إضافة الإيموجي {name}.",
        "ticket_open":     "🎫 تم إنشاء تذكرتك: {channel}",
        "ticket_exists":   "❌ لديك تذكرة مفتوحة بالفعل.",
        "lang_set":        "✅ تم ضبط اللغة على {lang}.",
        "antispam_ban":    "🔨 تم حظر {user} بسبب الرسائل المتكررة عبر القنوات.",
    },
    "th": {
        "no_perm":         "❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
        "kick_success":    "✅ {user} ถูกเตะออกแล้ว เหตุผล: {reason}",
        "ban_success":     "✅ {user} ถูกแบนแล้ว เหตุผล: {reason}",
        "timeout_success": "✅ {user} ถูก timeout {duration} นาที",
        "warn_success":    "⚠️ {user} ได้รับคำเตือน เหตุผล: {reason}",
        "role_add":        "✅ เพิ่มบทบาท {role} ให้ {user} แล้ว",
        "role_remove":     "✅ นำบทบาท {role} ออกจาก {user} แล้ว",
        "move_success":    "✅ ย้าย {user} ไปที่ {channel} แล้ว",
        "emoji_add":       "✅ เพิ่มอิโมจิ {name} แล้ว",
        "ticket_open":     "🎫 สร้างตั๋วของคุณแล้ว: {channel}",
        "ticket_exists":   "❌ คุณมีตั๋วที่เปิดอยู่แล้ว",
        "lang_set":        "✅ ตั้งภาษาเป็น {lang} แล้ว",
        "antispam_ban":    "🔨 {user} ถูกแบนเนื่องจากส่งข้อความซ้ำในหลายช่อง",
    },
    "vi": {
        "no_perm":         "❌ Bạn không có quyền sử dụng lệnh này.",
        "kick_success":    "✅ {user} đã bị kick. Lý do: {reason}",
        "ban_success":     "✅ {user} đã bị ban. Lý do: {reason}",
        "timeout_success": "✅ {user} đã bị timeout {duration} phút.",
        "warn_success":    "⚠️ {user} đã bị cảnh báo. Lý do: {reason}",
        "role_add":        "✅ Đã thêm vai trò {role} cho {user}.",
        "role_remove":     "✅ Đã xóa vai trò {role} khỏi {user}.",
        "move_success":    "✅ Đã chuyển {user} sang {channel}.",
        "emoji_add":       "✅ Đã thêm emoji {name}.",
        "ticket_open":     "🎫 Ticket của bạn đã được tạo: {channel}",
        "ticket_exists":   "❌ Bạn đã có ticket đang mở.",
        "lang_set":        "✅ Ngôn ngữ đã được đặt thành {lang}.",
        "antispam_ban":    "🔨 {user} đã bị ban do spam trên nhiều kênh.",
    },
    "ja": {
        "no_perm":         "❌ このコマンドを使用する権限がありません。",
        "kick_success":    "✅ {user} をキックしました。理由: {reason}",
        "ban_success":     "✅ {user} をBANしました。理由: {reason}",
        "timeout_success": "✅ {user} を{duration}分タイムアウトしました。",
        "warn_success":    "⚠️ {user} に警告を送りました。理由: {reason}",
        "role_add":        "✅ {user} にロール {role} を付与しました。",
        "role_remove":     "✅ {user} からロール {role} を削除しました。",
        "move_success":    "✅ {user} を {channel} に移動しました。",
        "emoji_add":       "✅ 絵文字 {name} を追加しました。",
        "ticket_open":     "🎫 チケットが作成されました: {channel}",
        "ticket_exists":   "❌ すでに開いているチケットがあります。",
        "lang_set":        "✅ 言語を {lang} に設定しました。",
        "antispam_ban":    "🔨 {user} は複数チャンネルへのスパムのためBANされました。",
    },
    "ko": {
        "no_perm":         "❌ 이 명령어를 사용할 권한이 없습니다.",
        "kick_success":    "✅ {user}을(를) 추방했습니다. 사유: {reason}",
        "ban_success":     "✅ {user}을(를) 차단했습니다. 사유: {reason}",
        "timeout_success": "✅ {user}을(를) {duration}분 타임아웃했습니다.",
        "warn_success":    "⚠️ {user}에게 경고를 보냈습니다. 사유: {reason}",
        "role_add":        "✅ {user}에게 역할 {role}을(를) 부여했습니다.",
        "role_remove":     "✅ {user}에게서 역할 {role}을(를) 제거했습니다.",
        "move_success":    "✅ {user}을(를) {channel}로 이동했습니다.",
        "emoji_add":       "✅ 이모지 {name}을(를) 추가했습니다.",
        "ticket_open":     "🎫 티켓이 생성되었습니다: {channel}",
        "ticket_exists":   "❌ 이미 열려 있는 티켓이 있습니다.",
        "lang_set":        "✅ 언어가 {lang}으로 설정되었습니다.",
        "antispam_ban":    "🔨 {user}이(가) 여러 채널에 스팸을 보내 차단되었습니다.",
    },
}

def t(cfg: dict, guild_id: int, key: str, **kwargs) -> str:
    gc   = guild_cfg(cfg, guild_id)
    lang = gc.get("language", "en")
    s    = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
    return s.format(**kwargs)

# ─────────────────────────────────────────────
# EMBED HELPERS
# ─────────────────────────────────────────────

def base_embed(title: str, description: str = "", color: int = EMBED_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text="JoyCannot Bot")
    e.timestamp = discord.utils.utcnow()
    return e

def success_embed(desc: str) -> discord.Embed:
    return base_embed("✅ Success", desc, 0x22C55E)

def error_embed(desc: str) -> discord.Embed:
    return base_embed("❌ Error", desc, 0xEF4444)

def info_embed(title: str, desc: str) -> discord.Embed:
    return base_embed(title, desc)

# ─────────────────────────────────────────────
# DURATION PARSER
# ─────────────────────────────────────────────

def parse_duration(s: str) -> Optional[int]:
    """'1h30m' → seconds (int). Returns None if invalid."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?", s.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60

def fmt_duration(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m      = rem // 60
    parts  = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return " ".join(parts) or "0m"

# ─────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────

intents                 = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True

cfg = load_config()

# ── Store original command descriptions for premium label system ──
# Must be declared BEFORE CommandTree subclass uses it.
ORIGINAL_CMD_DESCRIPTIONS: dict[str, str] = {}

# ── Pending payment proof tracker ──
# key: user_id (int) → value: dict with order info + asyncio.Event
pending_proofs: dict[int, dict] = {}

# ── Subclass CommandTree — the ONLY correct way to add a global slash check ──
class JoyCommandTree(app_commands.CommandTree):
    @staticmethod
    def _resolve_cmd_name(interaction: discord.Interaction) -> Optional[str]:
        """
        Resolve the qualified command name from raw interaction data.
        We CANNOT use interaction.command here because discord.py hasn't
        resolved it yet at the interaction_check stage — it would be None.
        So we read directly from interaction.data instead.

        Returns e.g. "kick", "ticket setup", "language set", or None.
        """
        data = getattr(interaction, "data", None)
        if not data:
            return None
        # interaction type 1 = PING, 2 = APP_COMMAND (slash), 3 = MESSAGE_COMPONENT, 4 = AUTOCOMPLETE, 5 = MODAL
        if interaction.type not in (
            discord.InteractionType.application_command,
            discord.InteractionType.autocomplete,
        ):
            return None
        # Application command type: 1 = CHAT_INPUT (slash), 2 = USER, 3 = MESSAGE
        if data.get("type", 1) != 1:
            return None  # Only intercept slash commands

        parts = [data.get("name", "")]
        # Walk into sub-command / sub-command-group options
        options = data.get("options", [])
        while options:
            opt = options[0]
            # option type 1 = SUB_COMMAND, 2 = SUB_COMMAND_GROUP
            if opt.get("type") in (1, 2):
                parts.append(opt["name"])
                options = opt.get("options", [])
            else:
                break
        return " ".join(parts) if parts else None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global gate: block non-premium users from premium-locked slash commands."""
        cmd_name = self._resolve_cmd_name(interaction)
        if not cmd_name:
            return True  # Not a slash command (button, modal, etc.) — always allow

        premium_cmds = cfg.get("premium_commands", [])
        if cmd_name not in premium_cmds:
            return True  # Command not locked — allow

        # ── Check premium access ──────────────────────────────────────────
        if user_has_premium(interaction.guild, interaction.user):
            return True

        # ── Blocked — respond ephemeral ────────────────────────────────────
        try:
            await interaction.response.send_message(
                embed=base_embed(
                    "💎 Premium Required",
                    f"The command `/{cmd_name}` is only available for **Premium** servers or users.\n\n"
                    "📦 Use `/premium info` to see available packages.\n"
                    "📩 Use `/premium order` to subscribe.",
                    color=0xF59E0B),
                ephemeral=True)
        except discord.InteractionResponded:
            pass
        return False

bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    help_command=None,
    owner_id=int(os.getenv("OWNER_ID", "0")),
    tree_cls=JoyCommandTree,
)

# ─────────────────────────────────────────────
# PREMIUM ACCESS HELPERS
# ─────────────────────────────────────────────

def user_has_premium(guild: Optional[discord.Guild], user: discord.abc.User) -> bool:
    """
    Return True if:
    - User ID is in the global premium_users list (individual premium), OR
    - The guild they're in is in premium_guilds (server-wide premium)
    """
    if user.id in cfg.get("premium_users", []):
        return True
    if guild and guild.id in cfg.get("premium_guilds", []):
        return True
    return False

PREMIUM_NICK      = "JoyCannot Premium"
PREMIUM_ROLE_NAME = "⭐ JoyCannot Premium"
PREMIUM_ROLE_COLOR = discord.Color(0xF59E0B)   # amber/yellow

async def set_guild_premium_nick(guild: discord.Guild, activate: bool):
    """
    Activate:
      1. Create role '⭐ JoyCannot Premium' (yellow) if not exists
      2. Assign it to the bot (above all other bot roles so color shows)
      3. Set bot nickname to 'JoyCannot Premium'

    Deactivate:
      1. Remove the premium role from the bot
      2. Delete the role from the server
      3. Reset bot nickname to None (original username)
    """
    me = guild.me
    try:
        if activate:
            # ── Find or create the premium role ──────────────────────────
            role = discord.utils.get(guild.roles, name=PREMIUM_ROLE_NAME)
            if not role:
                role = await guild.create_role(
                    name=PREMIUM_ROLE_NAME,
                    color=PREMIUM_ROLE_COLOR,
                    reason="JoyCannot Premium activation"
                )

            # ── Move role just below the bot's highest managed role ───────
            try:
                top_pos = max((r.position for r in me.roles if r.managed), default=1)
                await role.edit(position=max(top_pos - 1, 1))
            except Exception:
                pass   # Position edit may fail in some configs — not critical

            # ── Assign role to bot if not already ─────────────────────────
            if role not in me.roles:
                await me.add_roles(role, reason="JoyCannot Premium activation")

            # ── Set nickname ───────────────────────────────────────────────
            await me.edit(nick=PREMIUM_NICK)
            logging.info(f"[Premium] Activated in {guild.name} — role + nick set.")

        else:
            # ── Remove & delete the premium role ──────────────────────────
            role = discord.utils.get(guild.roles, name=PREMIUM_ROLE_NAME)
            if role:
                if role in me.roles:
                    await me.remove_roles(role, reason="JoyCannot Premium deactivation")
                try:
                    await role.delete(reason="JoyCannot Premium deactivation")
                except Exception:
                    pass

            # ── Reset nickname ─────────────────────────────────────────────
            await me.edit(nick=None)
            logging.info(f"[Premium] Deactivated in {guild.name} — role removed, nick reset.")

    except discord.Forbidden:
        logging.warning(f"[Premium] Missing permissions in {guild.name} ({guild.id})")
    except Exception as e:
        logging.error(f"[Premium] Error in {guild.name}: {e}")


async def set_bot_avatar(url: str) -> bool:
    """
    Fetch image from URL and set it as the bot's global avatar.
    Returns True on success, False on failure.
    Rate-limited by Discord: max ~2 times per 10 minutes.
    """
    if not url:
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logging.warning(f"[Avatar] Failed to fetch image: HTTP {resp.status}")
                    return False
                data = await resp.read()
        await bot.user.edit(avatar=data)
        logging.info(f"[Avatar] Bot avatar updated from {url}")
        return True
    except discord.HTTPException as e:
        logging.error(f"[Avatar] Discord error: {e}")
        return False
    except Exception as e:
        logging.error(f"[Avatar] Error: {e}")
        return False


def is_premium_command(cmd_name: str) -> bool:
    return cmd_name in cfg.get("premium_commands", [])

async def apply_premium_labels():
    """
    Update slash command descriptions to add/remove [💎] label, then sync.

    Strategy:
    - Modify local command tree descriptions
    - Sync per-guild first → instant effect in all current servers
    - Then global sync → covers future servers the bot joins
    Always reads from ORIGINAL_CMD_DESCRIPTIONS so labels never stack.
    """
    premium_cmds = set(cfg.get("premium_commands", []))

    for cmd in bot.tree.get_commands():
        base_name = cmd.name
        orig = ORIGINAL_CMD_DESCRIPTIONS.get(base_name)
        if orig is None:
            orig = cmd.description.removeprefix("[💎] ")
            ORIGINAL_CMD_DESCRIPTIONS[base_name] = orig
        cmd.description = (f"[💎] {orig}"[:100] if base_name in premium_cmds else orig)

        if hasattr(cmd, "commands"):
            for sub in cmd.commands:
                sub_full = f"{base_name} {sub.name}"
                sub_orig = ORIGINAL_CMD_DESCRIPTIONS.get(sub_full)
                if sub_orig is None:
                    sub_orig = sub.description.removeprefix("[💎] ")
                    ORIGINAL_CMD_DESCRIPTIONS[sub_full] = sub_orig
                sub.description = (f"[💎] {sub_orig}"[:100] if sub_full in premium_cmds else sub_orig)

    # ── Per-guild sync (instant, no propagation delay) ──
    guild_ok = guild_fail = 0
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
            guild_ok += 1
            await asyncio.sleep(0.3)   # avoid hitting rate limit
        except discord.HTTPException:
            guild_fail += 1
        except Exception:
            guild_fail += 1

    logging.info(f"[Premium Labels] Guild sync done — ✅ {guild_ok} / ❌ {guild_fail}. Locked: {premium_cmds}")

    # ── Global sync (covers new servers, may take ~1h to propagate) ──
    await asyncio.sleep(1)
    try:
        synced = await bot.tree.sync()
        logging.info(f"[Premium Labels] Global sync — {len(synced)} commands.")
    except discord.HTTPException as e:
        logging.error(f"[Premium Labels] Global sync HTTP error: {e}")
    except Exception as e:
        logging.error(f"[Premium Labels] Global sync error: {e}")

# ─────────────────────────────────────────────
# ANTI CROSS-CHANNEL SPAM
# ─────────────────────────────────────────────
#
# Fingerprint = normalized text + attachment filenames + URLs in message.
# We track: uid → fingerprint → {channel_ids, message_ids}
# When the same fingerprint appears in SPAM_THRESHOLD different channels
# within SPAM_WINDOW seconds → delete ALL tracked spam messages → ban user.
#
# Covers: plain text, invite links, image spam, file spam, mixed content.
# ─────────────────────────────────────────────

SPAM_THRESHOLD = 3      # How many different channels trigger a ban
SPAM_WINDOW    = 8.0    # Seconds within which the spread must happen

# uid → fingerprint → {"channels": set, "messages": list of (channel_id, message_id), "first_seen": float}
spam_tracker:       dict[int, dict[str, dict]] = defaultdict(dict)
spam_cleanup_times: dict[int, float]           = {}


def _spam_fingerprint(message: discord.Message) -> str:
    """
    Build a normalized fingerprint for a message that covers:
    - Text content (lowercased, stripped)
    - All attachment filenames (catches image/file spam)
    - All URLs found in the message (catches invite / link spam)
    - Embed URLs if present
    Returns a single string used as the tracker key.
    """
    parts: list[str] = []

    # ── Text ──────────────────────────────────────────────────────────────
    text = message.content.strip().lower()
    if text:
        parts.append(text)

    # ── Attachments (image, file, video, etc.) ────────────────────────────
    for att in message.attachments:
        # Use filename so same image with different URLs still matches
        parts.append(f"att:{att.filename.lower()}")

    # ── URLs extracted from text ──────────────────────────────────────────
    url_pattern = re.compile(
        r"(https?://[^\s]+|discord\.gg/[^\s]+|discord\.com/invite/[^\s]+)",
        re.IGNORECASE
    )
    for url in url_pattern.findall(message.content):
        # Normalize: strip tracking params, lowercase
        normalized = url.lower().split("?")[0].rstrip("/")
        parts.append(f"url:{normalized}")

    # ── Embeds (links auto-embedded by Discord) ───────────────────────────
    for embed in message.embeds:
        if embed.url:
            parts.append(f"url:{embed.url.lower().split('?')[0].rstrip('/')}")

    return "|".join(sorted(set(parts))) or "empty"

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  FIX #2 — SLASH COMMANDS VIA PREFIX TOO
#  We intercept non-owner prefix messages and
#  route them to the slash command tree.
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

OWNER_ONLY_CMDS = {"maintenance", "premium", "setchannel"}

# ── Global prefix premium gate ─────────────────────────────────────────────
@bot.check
async def global_prefix_premium_check(ctx: commands.Context) -> bool:
    """Block non-premium users from premium-locked prefix commands."""
    cmd_name = ctx.command.qualified_name if ctx.command else None
    if not cmd_name or cmd_name in OWNER_ONLY_CMDS:
        return True
    if cmd_name not in cfg.get("premium_commands", []):
        return True
    if user_has_premium(ctx.guild, ctx.author):
        return True
    return False  # → triggers CheckFailure → on_command_error

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[JoyCannot] Ready as {bot.user} (ID: {bot.user.id})")

    # ── Snapshot CLEAN original descriptions (strip any leftover [💎] prefix) ──
    for cmd in bot.tree.get_commands():
        raw = cmd.description.removeprefix("[💎] ")
        ORIGINAL_CMD_DESCRIPTIONS[cmd.name] = raw
        if hasattr(cmd, "commands"):
            for sub in cmd.commands:
                sub_raw = sub.description.removeprefix("[💎] ")
                ORIGINAL_CMD_DESCRIPTIONS[f"{cmd.name} {sub.name}"] = sub_raw

    # ── Initial global sync ──
    try:
        synced = await bot.tree.sync()
        print(f"[JoyCannot] Global sync: {len(synced)} command(s).")
    except Exception as e:
        print(f"[JoyCannot] Global sync error: {e}")

    # ── Re-apply saved premium labels immediately (per-guild for instant effect) ──
    if cfg.get("premium_commands"):
        print("[JoyCannot] Applying premium labels...")
        await apply_premium_labels()

    cleanup_spam_cache.start()
    rotate_status.start()
    print(f"[JoyCannot] Ready — {len(bot.guilds)} guild(s).")

    # ── Restore premium nicknames for all activated guilds ──
    premium_guilds = set(cfg.get("premium_guilds", []))
    if premium_guilds:
        print(f"[JoyCannot] Restoring premium nicknames for {len(premium_guilds)} guild(s)...")
        for guild in bot.guilds:
            if guild.id in premium_guilds:
                await set_guild_premium_nick(guild, activate=True)
                await asyncio.sleep(0.5)

    # ── Restore correct avatar based on premium state ──
    has_premium = len(cfg.get("premium_guilds", [])) > 0
    avatar_url  = cfg.get("avatar_premium" if has_premium else "avatar_default", "")
    if avatar_url:
        ok = await set_bot_avatar(avatar_url)
        print(f"[JoyCannot] Avatar {'restored ✅' if ok else 'restore failed ❌'} ({'premium' if has_premium else 'default'})")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Welcome embed when bot joins a server."""
    gc = guild_cfg(cfg, guild.id)

    target = guild.system_channel
    if not target:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                target = ch
                break
    if not target:
        return

    embed = base_embed(
        "👋 Thanks for inviting JoyCannot!",
        "Hello! I'm **JoyCannot**, a professional multi-purpose Discord bot.\n\n"
        "**Features:**\n"
        "🛡️ Full Moderation Suite\n"
        "🎫 Advanced Ticket System\n"
        "📅 Live Countdown Event System\n"
        "📢 Maintenance Broadcasts\n"
        "🌐 Multi-language Support (8 languages)\n"
        "💎 Premium Package System\n"
        "🚫 Anti Cross-Channel Spam\n\n"
        "Use `/help` or `!Joy help` to get started!\n\n"
        "**Setup:** Select the main channel below for maintenance notifications."
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    class ChannelSelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)

        @discord.ui.select(
            cls=discord.ui.ChannelSelect,
            channel_types=[discord.ChannelType.text],
            placeholder="📌 Select main notification channel",
            min_values=1, max_values=1,
        )
        async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    embed=error_embed("Only administrators can set the main channel."), ephemeral=True)
                return
            gc["main_channel"] = select.values[0].id
            save_config(cfg)
            await interaction.response.send_message(
                embed=success_embed(f"Main channel set to {select.values[0].mention}!"), ephemeral=True)
            self.stop()

    await target.send(embed=embed, view=ChannelSelectView())


# NOTE: on_message is defined further below in the XP/Leveling section
# to combine anti-spam + XP/quest processing + prefix routing in one handler.


async def _try_delete(channel: discord.TextChannel, message_id: int):
    """Silently attempt to delete a message by ID."""
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


# ─────────────────────────────────────────────
# BACKGROUND TASKS
# ─────────────────────────────────────────────

@tasks.loop(seconds=10)
async def cleanup_spam_cache():
    """Remove expired spam tracking entries to prevent memory leak."""
    now   = discord.utils.utcnow().timestamp()
    stale_users = [u for u, ts in spam_cleanup_times.items() if now - ts > SPAM_WINDOW * 2]
    for uid in stale_users:
        spam_tracker.pop(uid, None)
        spam_cleanup_times.pop(uid, None)


_status_index = 0

@tasks.loop(seconds=20)
async def rotate_status():
    """Rotate bot status every 20 seconds for a professional presence."""
    global _status_index
    guild_count   = len(bot.guilds)
    premium_count = len(cfg.get("premium_guilds", []))
    statuses = [
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"{guild_count} servers"),
        discord.Activity(type=discord.ActivityType.listening,
                         name="/help • !Joy help"),
        discord.Activity(type=discord.ActivityType.playing,
                         name="JoyCannot v1.3 🚀"),
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"{premium_count} premium server{'s' if premium_count != 1 else ''}"),
        discord.Activity(type=discord.ActivityType.listening,
                         name="/vote → get discount 🗳️"),
        discord.Activity(type=discord.ActivityType.watching,
                         name="for cross-channel spam 🛡️"),
    ]
    activity = statuses[_status_index % len(statuses)]
    _status_index += 1
    try:
        await bot.change_presence(status=discord.Status.online, activity=activity)
    except Exception:
        pass

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  SHARED COMMAND LOGIC
#  Each feature has a core async function.
#  Both slash AND prefix commands call these.
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

async def do_kick(guild, author, member, reason, reply_fn):
    if not author.guild_permissions.kick_members:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        await member.kick(reason=reason)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "kick_success", user=member.mention, reason=reason)))
    except discord.Forbidden:
        await reply_fn(embed=error_embed("I lack permission to kick this user."), ephemeral=True)

async def do_ban(guild, author, member, reason, reply_fn):
    if not author.guild_permissions.ban_members:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        await member.ban(reason=reason, delete_message_days=1)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "ban_success", user=member.mention, reason=reason)))
    except discord.Forbidden:
        await reply_fn(embed=error_embed("I lack permission to ban this user."), ephemeral=True)

async def do_timeout(guild, author, member, minutes, reason, reply_fn):
    if not author.guild_permissions.moderate_members:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "timeout_success", user=member.mention, duration=minutes)))
    except discord.Forbidden:
        await reply_fn(embed=error_embed("I lack permission to timeout this user."), ephemeral=True)

async def do_warn(guild, author, member, reason, reply_fn):
    if not author.guild_permissions.manage_messages:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    gc  = guild_cfg(cfg, guild.id)
    uid = str(member.id)
    gc["warnings"].setdefault(uid, []).append({
        "reason": reason,
        "timestamp": discord.utils.utcnow().isoformat(),
        "warned_by": author.id
    })
    save_config(cfg)
    await reply_fn(embed=success_embed(t(cfg, guild.id, "warn_success", user=member.mention, reason=reason)))
    try:
        await member.send(embed=base_embed("⚠️ You have been warned",
            f"**Server:** {guild.name}\n**Reason:** {reason}"))
    except Exception:
        pass

async def do_addrole(guild, author, member, role, reply_fn):
    if not author.guild_permissions.manage_roles:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        await member.add_roles(role)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "role_add", role=role.mention, user=member.mention)))
    except discord.Forbidden:
        await reply_fn(embed=error_embed("I lack permission to manage roles."), ephemeral=True)

async def do_removerole(guild, author, member, role, reply_fn):
    if not author.guild_permissions.manage_roles:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        await member.remove_roles(role)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "role_remove", role=role.mention, user=member.mention)))
    except discord.Forbidden:
        await reply_fn(embed=error_embed("I lack permission to manage roles."), ephemeral=True)

async def do_move(guild, author, member, channel, reply_fn):
    if not author.guild_permissions.move_members:
        return await reply_fn(embed=error_embed(t(cfg, guild.id, "no_perm")), ephemeral=True)
    try:
        await member.move_to(channel)
        await reply_fn(embed=success_embed(t(cfg, guild.id, "move_success", user=member.mention, channel=channel.mention)))
    except (discord.Forbidden, discord.HTTPException) as e:
        await reply_fn(embed=error_embed(str(e)), ephemeral=True)

async def do_userinfo(guild, member, reply_fn):
    gc    = guild_cfg(cfg, guild.id)
    warns = len(gc["warnings"].get(str(member.id), []))
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed = base_embed(f"👤 User Info — {member.display_name}")
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Username",   value=str(member),                                   inline=True)
    embed.add_field(name="ID",         value=str(member.id),                                inline=True)
    embed.add_field(name="Joined",     value=discord.utils.format_dt(member.joined_at,"R"), inline=True)
    embed.add_field(name="Registered", value=discord.utils.format_dt(member.created_at,"R"),inline=True)
    embed.add_field(name="Warnings",   value=str(warns),                                    inline=True)
    embed.add_field(name="Top Role",   value=member.top_role.mention,                       inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) or "None",          inline=False)
    await reply_fn(embed=embed)

async def do_avatar(member, reply_fn):
    embed = base_embed(f"🖼️ Avatar — {member.display_name}")
    embed.set_image(url=member.display_avatar.url)
    await reply_fn(embed=embed)

async def do_ping(reply_fn):
    await reply_fn(embed=info_embed("🏓 Pong!", f"Websocket latency: **{round(bot.latency*1000)}ms**"))

async def do_help(reply_fn):
    pc = set(cfg.get("premium_commands", []))
    def lbl(name: str) -> str:
        return f"`{name}` 💎" if name in pc else f"`{name}`"

    embed = base_embed("📖 JoyCannot — Command List",
        "All commands work as `/slash` **and** `!Joy prefix`.\n"
        "💎 = Premium required")
    embed.add_field(name="🛡️ Moderation", value=(
        f"{lbl('kick')} {lbl('ban')} {lbl('timeout')} {lbl('warn')}\n"
        f"{lbl('addrole')} {lbl('removerole')} {lbl('move')}\n"
        f"{lbl('userinfo')} {lbl('avatar')} {lbl('addemoji')} {lbl('ping')}"
    ), inline=False)
    embed.add_field(name="🎫 Tickets", value=(
        f"{lbl('ticket setup')} · {lbl('ticket panel')} · {lbl('ticket close')}"
    ), inline=False)
    embed.add_field(name="📅 Events", value=(
        f"{lbl('event create')} · {lbl('event channel')}"
    ), inline=False)
    embed.add_field(name="🌐 Language", value=(
        f"{lbl('language set')} · {lbl('language list')}"
    ), inline=False)
    embed.add_field(name="💎 Premium", value=(
        f"{lbl('premium info')} · {lbl('premium order')}"
    ), inline=False)
    embed.add_field(name="👑 Owner Only (prefix)", value=(
        "`!Joy maintenance` · `!Joy premium` · `!Joy setchannel`"
    ), inline=False)
    await reply_fn(embed=embed)

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  AUTOCOMPLETE CALLBACKS
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

async def autocomplete_lang(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for language codes."""
    return [
        app_commands.Choice(name=f"{code} — {name}", value=code)
        for code, name in LANGUAGES.items()
        if current.lower() in code.lower() or current.lower() in name.lower()
    ][:25]

async def autocomplete_package(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for premium package names."""
    packages = cfg.get("premium_packages", [])
    return [
        app_commands.Choice(
            name=f"{p['name']} — {p.get('duration','?')} — {p.get('price','?')}",
            value=p["name"]
        )
        for p in packages
        if current.lower() in p["name"].lower()
    ][:25]

async def autocomplete_timeout_minutes(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    """Autocomplete common timeout durations."""
    presets = [
        (5,    "5 minutes"),
        (10,   "10 minutes"),
        (30,   "30 minutes"),
        (60,   "1 hour"),
        (120,  "2 hours"),
        (360,  "6 hours"),
        (720,  "12 hours"),
        (1440, "1 day"),
        (4320, "3 days"),
        (10080,"7 days"),
    ]
    results = []
    for val, label in presets:
        if not current or current in str(val) or current.lower() in label.lower():
            results.append(app_commands.Choice(name=label, value=val))
    return results[:25]

async def autocomplete_warn_reason(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete common warn reasons."""
    reasons = [
        "Spam",
        "Toxic behaviour",
        "Hate speech",
        "NSFW content",
        "Self-promotion / advertising",
        "Flood / mass ping",
        "Inappropriate nickname",
        "Off-topic",
        "Misinformation",
        "Evading mute/ban",
    ]
    return [
        app_commands.Choice(name=r, value=r)
        for r in reasons
        if current.lower() in r.lower()
    ][:25]

async def autocomplete_ban_reason(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete common ban reasons."""
    reasons = [
        "Hate speech / discrimination",
        "Raiding / server disruption",
        "Doxxing / sharing personal info",
        "Extreme harassment",
        "CSAM or illegal content",
        "Bot / selfbot usage",
        "Scamming members",
        "Evading previous ban",
        "Threats of violence",
        "Repeated rule violations",
    ]
    return [
        app_commands.Choice(name=r, value=r)
        for r in reasons
        if current.lower() in r.lower()
    ][:25]

async def do_addemoji(guild: discord.Guild, emoji_or_url: str, name: str = "") -> dict:
    """
    Add an emoji to a guild. Supports three modes:
      1. Custom Discord emoji  <:name:id> or <a:name:id>
      2. Unicode/native emoji  😁 🔥 etc  (fetched from Twemoji CDN)
      3. Direct image URL      https://...
    """
    import aiohttp, unicodedata

    src = emoji_or_url.strip()

    # ── Mode 1: Custom Discord emoji <:name:id> or <a:name:id> ────────────
    emoji_re = re.fullmatch(r"<(a?):([a-zA-Z0-9_]+):(\d+)>", src)
    if emoji_re:
        animated   = emoji_re.group(1) == "a"
        emoji_name = name.strip() or emoji_re.group(2)
        emoji_id   = emoji_re.group(3)
        ext        = "gif" if animated else "png"
        cdn_url    = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128&quality=lossless"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cdn_url) as resp:
                    if resp.status != 200:
                        return {"success": False, "error": f"Could not fetch emoji from Discord CDN (HTTP {resp.status})."}
                    data = await resp.read()
            emoji = await guild.create_custom_emoji(name=emoji_name, image=data)
            return {"success": True, "emoji": emoji}
        except discord.HTTPException as e:
            return {"success": False, "error": f"Discord error: {e.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Mode 2: Unicode/native emoji 😁 🔥 ──────────────────────────────
    def _is_unicode_emoji(s: str) -> bool:
        if s.startswith("http") or s.startswith("<"):
            return False
        for ch in s:
            if ord(ch) < 0x00A0:
                return False
        return True

    if _is_unicode_emoji(src):
        if not name.strip():
            try:
                auto_name = unicodedata.name(src[0], "emoji").replace(" ", "_").replace("-", "_").lower()
                emoji_name = re.sub(r"[^a-z0-9_]", "", auto_name)[:32] or "emoji"
            except Exception:
                emoji_name = "emoji"
        else:
            emoji_name = name.strip()
        codepoints = [f"{ord(c):x}" for c in src if ord(c) != 0xFE0F]
        twemoji_url = "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/" + "-".join(codepoints) + ".png"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(twemoji_url) as resp:
                    if resp.status != 200:
                        codepoints2 = [f"{ord(c):x}" for c in src if ord(c) not in (0xFE0F, 0x200D)]
                        twemoji_url2 = "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/" + "-".join(codepoints2) + ".png"
                        async with session.get(twemoji_url2) as resp2:
                            if resp2.status != 200:
                                return {"success": False, "error": f"Emoji `{src}` not found. Try `<:name:id>` or a URL instead."}
                            data = await resp2.read()
                    else:
                        data = await resp.read()
            emoji = await guild.create_custom_emoji(name=emoji_name, image=data)
            return {"success": True, "emoji": emoji}
        except discord.HTTPException as e:
            return {"success": False, "error": f"Discord error: {e.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Mode 3: Direct image URL ──────────────────────────────────────────
    url = src
    if not name.strip():
        return {"success": False,
                "error": "Please provide a **name** when using a URL.\n"
                         "Usage: `!Joy addemoji <url> <name>`\n"
                         "Or: `!Joy addemoji 😁 name` / `!Joy addemoji <:emoji:id>`"}
    if not url.startswith("http"):
        return {"success": False,
                "error": "Invalid input. Use:\n• `<:name:id>` — custom Discord emoji\n"
                         "• `😁 name` — native emoji\n• `https://...` — image URL"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"Could not fetch image (HTTP {resp.status})."}
                data = await resp.read()
        emoji = await guild.create_custom_emoji(name=name.strip(), image=data)
        return {"success": True, "emoji": emoji}
    except discord.HTTPException as e:
        return {"success": False, "error": f"Discord error: {e.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  SLASH COMMANDS
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

# ── MODERATION ────────────────────────────────

@bot.tree.command(name="kick", description="Kick a member from the server. Requires Kick Members permission.")
@app_commands.describe(
    member="The member you want to kick from this server",
    reason="Reason for the kick (shown in audit log)"
)
async def slash_kick(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_kick(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="ban", description="Permanently ban a member. Requires Ban Members permission.")
@app_commands.describe(
    member="The member you want to ban from this server",
    reason="Reason for the ban (shown in audit log & DM'd to user)"
)
@app_commands.autocomplete(reason=autocomplete_ban_reason)
async def slash_ban(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_ban(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="timeout", description="Temporarily mute a member. Requires Moderate Members permission.")
@app_commands.describe(
    member="The member to put in timeout",
    minutes="Duration of the timeout (pick a preset or type a custom value in minutes)",
    reason="Reason for the timeout"
)
@app_commands.autocomplete(minutes=autocomplete_timeout_minutes)
async def slash_timeout(i: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided."):
    await do_timeout(i.guild, i.user, member, minutes, reason, i.response.send_message)

@bot.tree.command(name="warn", description="Issue a formal warning to a member. Warnings are logged.")
@app_commands.describe(
    member="The member to warn",
    reason="Reason for the warning (DM'd to the member automatically)"
)
@app_commands.autocomplete(reason=autocomplete_warn_reason)
async def slash_warn(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_warn(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="addrole", description="Assign a role to a member. Requires Manage Roles permission.")
@app_commands.describe(
    member="The member who will receive the role",
    role="The role to assign (must be lower than the bot's highest role)"
)
async def slash_addrole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    await do_addrole(i.guild, i.user, member, role, i.response.send_message)

@bot.tree.command(name="removerole", description="Remove a role from a member. Requires Manage Roles permission.")
@app_commands.describe(
    member="The member to remove the role from",
    role="The role to remove from the member"
)
async def slash_removerole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    await do_removerole(i.guild, i.user, member, role, i.response.send_message)

@bot.tree.command(name="move", description="Move a member to a different voice channel. Requires Move Members.")
@app_commands.describe(
    member="The member currently in a voice channel",
    channel="The destination voice channel"
)
async def slash_move(i: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    await do_move(i.guild, i.user, member, channel, i.response.send_message)

@bot.tree.command(name="userinfo", description="View detailed info about a member: roles, warnings, join date, and more.")
@app_commands.describe(
    member="Member to inspect (leave blank to view your own info)"
)
async def slash_userinfo(i: discord.Interaction, member: Optional[discord.Member] = None):
    await do_userinfo(i.guild, member or i.user, i.response.send_message)

@bot.tree.command(name="avatar", description="Show a member's full-size avatar image.")
@app_commands.describe(
    member="Member whose avatar to display (leave blank for your own)"
)
async def slash_avatar(i: discord.Interaction, member: Optional[discord.Member] = None):
    await do_avatar(member or i.user, i.response.send_message)

@bot.tree.command(name="ping", description="Check the bot's current websocket latency in milliseconds.")
async def slash_ping(i: discord.Interaction):
    await do_ping(i.response.send_message)

@bot.tree.command(name="help", description="Show all available commands with descriptions and premium status.")
async def slash_help(i: discord.Interaction):
    await do_help(i.response.send_message)

@bot.tree.command(name="addemoji", description="Add an emoji to this server — paste an emoji directly OR provide a name + image URL.")
@app_commands.describe(
    emoji_or_url="Paste an emoji from another server (e.g. <:name:id>) OR a direct image URL",
    name="Custom name for the emoji (required only when using a URL, not needed for pasted emoji)"
)
async def slash_addemoji(i: discord.Interaction, emoji_or_url: str, name: str = ""):
    if not i.user.guild_permissions.manage_emojis:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    await i.response.defer()
    result = await do_addemoji(i.guild, emoji_or_url, name)
    if result["success"]:
        emoji = result["emoji"]
        await i.followup.send(embed=success_embed(
            t(cfg, i.guild.id, "emoji_add", name=emoji.name) + f" {emoji}"))
    else:
        await i.followup.send(embed=error_embed(result["error"]), ephemeral=True)

# ── LANGUAGE ──────────────────────────────────

lang_group = app_commands.Group(name="language", description="Change or view the bot's language for this server.")

@lang_group.command(name="set", description="Set the bot's response language for this server. Requires Manage Server.")
@app_commands.describe(
    lang="Language code — start typing to search (e.g. 'id' for Indonesian, 'en' for English)"
)
@app_commands.autocomplete(lang=autocomplete_lang)
async def slash_lang_set(i: discord.Interaction, lang: str):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    if lang not in LANGUAGES:
        return await i.response.send_message(
            embed=error_embed(f"Valid codes: {', '.join(LANGUAGES.keys())}"), ephemeral=True)
    guild_cfg(cfg, i.guild.id)["language"] = lang
    save_config(cfg)
    await i.response.send_message(embed=success_embed(t(cfg, i.guild.id, "lang_set", lang=LANGUAGES[lang])))

@lang_group.command(name="list", description="Show all 8 supported languages and highlight the currently active one.")
async def slash_lang_list(i: discord.Interaction):
    cur   = guild_cfg(cfg, i.guild.id).get("language", "en")
    lines = "\n".join(f"{'✅' if k==cur else '◽'} `{k}` — {v}" for k, v in LANGUAGES.items())
    await i.response.send_message(embed=info_embed("🌐 Supported Languages", lines))

bot.tree.add_command(lang_group)

# ── TICKET ────────────────────────────────────

ticket_group = app_commands.Group(name="ticket", description="Manage the server's ticket support system.")

@ticket_group.command(name="setup", description="Configure the ticket system: category, log channel, support staff role, and ticket limits.")
@app_commands.describe(
    category="The category where new ticket channels will be created",
    log_channel="Channel where ticket open/close events are logged",
    support_role="Role for admins/ticket support staff — they get auto-access to every ticket",
    max_tickets="Max open tickets per user at a time (default: 1, max: 5)"
)
async def slash_ticket_setup(
    i: discord.Interaction,
    category: discord.CategoryChannel,
    log_channel: discord.TextChannel,
    support_role: Optional[discord.Role] = None,
    max_tickets: int = 1
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    if not (1 <= max_tickets <= 5):
        return await i.response.send_message(embed=error_embed("Max tickets must be between 1 and 5."), ephemeral=True)
    gc = guild_cfg(cfg, i.guild.id)
    gc["ticket"]["category"]     = category.id
    gc["ticket"]["log_channel"]  = log_channel.id
    gc["ticket"]["support_role"] = support_role.id if support_role else None
    gc["ticket"]["max_tickets"]  = max_tickets
    save_config(cfg)

    embed = base_embed("✅ Ticket System Configured",
        "Ticket system has been set up successfully!")
    embed.add_field(name="📁 Category",     value=category.name,                                            inline=True)
    embed.add_field(name="📋 Log Channel",  value=log_channel.mention,                                      inline=True)
    embed.add_field(name="🎭 Support Role", value=support_role.mention if support_role else "Anyone with Manage Channels", inline=True)
    embed.add_field(name="🎫 Max Tickets",  value=f"{max_tickets} per user",                                inline=True)
    await i.response.send_message(embed=embed)

@ticket_group.command(name="panel", description="Send a ticket panel embed with an 'Open Ticket' button to this channel.")
@app_commands.describe(
    title="Title shown on the ticket panel embed",
    description="Description text shown on the ticket panel embed",
    button_label="Label for the button users click to open a ticket"
)
async def slash_ticket_panel(
    i: discord.Interaction,
    title: str = "🎫 Support Tickets",
    description: str = "Click the button below to open a support ticket.",
    button_label: str = "Open Ticket"
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    gc = guild_cfg(cfg, i.guild.id)
    if not gc["ticket"].get("category"):
        return await i.response.send_message(embed=error_embed("Run `/ticket setup` first."), ephemeral=True)

    class TicketView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @discord.ui.button(label=button_label, style=discord.ButtonStyle.primary,
                           emoji="🎫", custom_id="joy_ticket_open")
        async def open_ticket(self, interaction: discord.Interaction, _btn):
            await handle_open_ticket(interaction)

    embed = base_embed(title, description)
    await i.response.send_message(embed=embed, view=TicketView())
    gc["ticket"]["panels"].append({"channel_id": i.channel.id, "title": title})
    save_config(cfg)

@ticket_group.command(name="close", description="Close this ticket. You'll be asked for a reason (required).")
async def slash_ticket_close(i: discord.Interaction):
    gc = guild_cfg(cfg, i.guild.id)
    for uid, ch_id in list(gc["active_tickets"].items()):
        if ch_id == i.channel.id:
            if not (i.user.guild_permissions.manage_channels or str(i.user.id) == uid):
                return await i.response.send_message(embed=error_embed("You cannot close this ticket."), ephemeral=True)
            return await i.response.send_modal(TicketCloseModal(uid))
    await i.response.send_message(embed=error_embed("This channel is not a ticket."), ephemeral=True)

bot.tree.add_command(ticket_group)


class TicketCloseModal(discord.ui.Modal, title="🔒 Close Ticket"):
    """Shown when closing a ticket — requires a reason."""
    reason = discord.ui.TextInput(
        label="Reason for closing",
        placeholder="e.g. Issue resolved, No response from user, Duplicate ticket...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=300
    )

    def __init__(self, opener_uid: str):
        super().__init__()
        self.opener_uid = opener_uid

    async def on_submit(self, i: discord.Interaction):
        reason_text = self.reason.value.strip()
        gc = guild_cfg(cfg, i.guild.id)

        close_embed = base_embed(
            "🔒 Ticket Closing",
            f"This ticket is being closed by {i.user.mention}.\n"
            f"**Reason:** {reason_text}\n\n"
            "Channel will be deleted in **5 seconds**.",
            color=0xEF4444
        )
        await i.response.send_message(embed=close_embed)

        # ── Log to log channel ────────────────────────────────────────────
        log_id = gc["ticket"].get("log_channel")
        if log_id:
            log_ch = i.guild.get_channel(log_id)
            if log_ch:
                log_embed = base_embed(
                    "📋 Ticket Closed",
                    None,
                    color=0xEF4444
                )
                log_embed.add_field(name="🎫 Channel",   value=i.channel.name,           inline=True)
                log_embed.add_field(name="🔒 Closed by", value=i.user.mention,            inline=True)
                log_embed.add_field(name="📝 Reason",    value=reason_text,               inline=False)
                log_embed.add_field(name="🕐 Time",
                    value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=False)
                # Find opener
                opener = i.guild.get_member(int(self.opener_uid)) if self.opener_uid.isdigit() else None
                if opener:
                    log_embed.add_field(name="👤 Opened by", value=opener.mention, inline=True)
                try:
                    await log_ch.send(embed=log_embed)
                except Exception:
                    pass

        await asyncio.sleep(5)
        if self.opener_uid in gc["active_tickets"]:
            del gc["active_tickets"][self.opener_uid]
            save_config(cfg)
        try:
            await i.channel.delete(reason=f"Ticket closed by {i.user} — {reason_text}")
        except Exception:
            pass


async def handle_open_ticket(i: discord.Interaction):
    gc  = guild_cfg(cfg, i.guild.id)
    uid = str(i.user.id)

    # ── Max tickets check ─────────────────────────────────────────────────
    max_tickets = gc["ticket"].get("max_tickets", 1)
    user_tickets = [ch_id for u, ch_id in gc["active_tickets"].items()
                    if u == uid and i.guild.get_channel(ch_id)]
    if len(user_tickets) >= max_tickets:
        if max_tickets == 1:
            existing_ch = i.guild.get_channel(user_tickets[0])
            msg = (f"You already have an open ticket: {existing_ch.mention if existing_ch else 'unknown channel'}.\n"
                   f"Please close it before opening a new one.")
        else:
            msg = (f"You have reached the maximum of **{max_tickets}** open tickets.\n"
                   f"Please close one before opening a new one.")
        return await i.response.send_message(embed=base_embed(
            "🎫 Ticket Limit Reached", msg, color=0xF59E0B), ephemeral=True)

    # Clean up stale ticket records where channel no longer exists
    stale = [u for u, ch_id in gc["active_tickets"].items()
             if u == uid and not i.guild.get_channel(ch_id)]
    for u in stale:
        del gc["active_tickets"][u]
    if stale:
        save_config(cfg)

    category = i.guild.get_channel(gc["ticket"].get("category"))
    if not category:
        return await i.response.send_message(embed=error_embed(
            "❌ Ticket category not configured.\nAsk an admin to run `/ticket setup` first."), ephemeral=True)

    safe = re.sub(r"[^a-z0-9]", "", i.user.name.lower()) or "user"
    ticket_num = len(gc["active_tickets"]) + 1

    # ── Build permission overwrites ───────────────────────────────────────
    ovw = {
        i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        i.user:               discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        i.guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    sr_id = gc["ticket"].get("support_role")
    support_role = i.guild.get_role(sr_id) if sr_id else None
    if support_role:
        ovw[support_role] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_messages=True, attach_files=True)

    ch = await i.guild.create_text_channel(
        f"ticket-{ticket_num:04d}-{safe}",
        category=category,
        overwrites=ovw,
        topic=f"Ticket opened by {i.user} ({i.user.id})"
    )
    gc["active_tickets"][uid] = ch.id
    save_config(cfg)

    await i.response.send_message(
        embed=base_embed(
            "🎫 Ticket Created",
            f"Your ticket has been created: {ch.mention}\nOur support team will assist you shortly.",
            color=0x22C55E
        ), ephemeral=True)

    # ── Professional welcome embed ────────────────────────────────────────
    sr_mention = support_role.mention if support_role else ""

    class CloseView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger,
                           emoji="🔒", custom_id=f"joy_ticket_close_{ch.id}")
        async def close_btn(self, interaction: discord.Interaction, _btn):
            # Check permission
            can_close = (
                interaction.user.guild_permissions.manage_channels
                or interaction.user.id == i.user.id
                or (support_role and support_role in interaction.user.roles)
            )
            if not can_close:
                return await interaction.response.send_message(
                    embed=error_embed("❌ You don't have permission to close this ticket."),
                    ephemeral=True)
            # Find opener uid
            inner = guild_cfg(cfg, interaction.guild.id)
            opener_uid = next(
                (k for k, v in inner["active_tickets"].items() if v == interaction.channel.id), uid)
            await interaction.response.send_modal(TicketCloseModal(opener_uid))

    welcome = discord.Embed(
        title=f"🎫 Ticket #{ticket_num:04d}",
        description=(
            f"Hello {i.user.mention}, welcome to your support ticket!\n\n"
            f"{'📣 ' + sr_mention + ' has been notified.' if sr_mention else '📣 Support staff has been notified.'}\n\n"
            f"**Please describe your issue in detail** and our team will assist you as soon as possible.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 Click **Close Ticket** when your issue is resolved."
        ),
        color=EMBED_COLOR
    )
    welcome.add_field(name="👤 Opened by",  value=f"{i.user.mention} (`{i.user.id}`)", inline=True)
    welcome.add_field(name="🕐 Opened at",  value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=True)
    welcome.set_thumbnail(url=i.user.display_avatar.url)
    welcome.set_footer(text="JoyCannot Ticket System • Close with reason when resolved")

    await ch.send(
        content=sr_mention if sr_mention else None,
        embed=welcome,
        view=CloseView()
    )

    # ── Log ───────────────────────────────────────────────────────────────
    log_id = gc["ticket"].get("log_channel")
    if log_id:
        log_ch = i.guild.get_channel(log_id)
        if log_ch:
            log_embed = base_embed("📋 Ticket Opened", None, color=0x22C55E)
            log_embed.add_field(name="🎫 Ticket",    value=f"{ch.mention} (#{ticket_num:04d})", inline=True)
            log_embed.add_field(name="👤 Opened by", value=f"{i.user.mention} (`{i.user.id}`)", inline=True)
            log_embed.add_field(name="🕐 Time",
                value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=False)
            try:
                await log_ch.send(embed=log_embed)
            except Exception:
                pass

# ── PREMIUM (slash) ───────────────────────────

premium_slash = app_commands.Group(name="premium", description="View and order JoyCannot Premium packages.")

@premium_slash.command(name="info", description="View all available premium packages, prices, durations, and payment methods.")
async def slash_premium_info(i: discord.Interaction):
    packages = cfg.get("premium_packages", [])
    if not packages:
        return await i.response.send_message(
            embed=info_embed("💎 Premium", "No packages available yet."), ephemeral=True)
    embed = base_embed("💎 JoyCannot Premium", "Upgrade your server!")
    for p in packages:
        embed.add_field(
            name=f"{'⭐' if p.get('type','')=='basic' else '💎'} {p['name']}",
            value=f"**Duration:** {p.get('duration','N/A')}\n**Type:** {p.get('type','N/A')}\n**Price:** {p.get('price','N/A')}",
            inline=True
        )
    pm = cfg.get("payment_methods", {})
    pay_lines = []
    for key, data in pm.items():
        if not (isinstance(data, dict) and data.get("enabled")):
            continue
        if key == "qris":
            info_txt = data.get("info") or "Available"
            pay_lines.append(f"✅ **QRIS** — {info_txt}")
        elif key == "bank":
            bn = data.get("bank_name") or "-"
            an = data.get("account_number") or "-"
            anm = data.get("account_name") or "-"
            pay_lines.append(f"✅ **Bank Transfer** — {bn} · `{an}` a/n {anm}")
        elif key == "ewallet":
            etype = data.get("type") or "-"
            num   = data.get("number") or "-"
            pay_lines.append(f"✅ **E-Wallet** ({etype}) — `{num}`")
    embed.add_field(name="💳 Payment Methods",
        value="\n".join(pay_lines) if pay_lines else "No payment methods enabled.", inline=False)
    await i.response.send_message(embed=embed)

@premium_slash.command(name="order", description="Order a premium package — pick your package and payment method to submit an order.")
@app_commands.describe(
    package_name="Name of the package to order (start typing to see available options)",
    payment="Your preferred payment method"
)
@app_commands.autocomplete(package_name=autocomplete_package)
@app_commands.choices(payment=[
    app_commands.Choice(name="QRIS",          value="qris"),
    app_commands.Choice(name="Bank Transfer", value="bank"),
    app_commands.Choice(name="E-Wallet",      value="ewallet"),
])
async def slash_premium_order(i: discord.Interaction, package_name: str, payment: str):
    pkg = next((p for p in cfg.get("premium_packages", []) if p["name"].lower() == package_name.lower()), None)
    if not pkg:
        return await i.response.send_message(embed=error_embed("Package not found. Use `/premium info`."), ephemeral=True)
    pm_entry = cfg.get("payment_methods", {}).get(payment, {})
    if not (isinstance(pm_entry, dict) and pm_entry.get("enabled")):
        return await i.response.send_message(embed=error_embed("Payment method not available."), ephemeral=True)

    # ── Vote discount check ───────────────────────────────────────────────
    discount_pct  = get_vote_discount(i.user.id)
    original_price = pkg.get("price", "N/A")
    if discount_pct > 0:
        # Try to parse numeric price for discount calculation
        price_str = original_price
        import re as _re
        nums = _re.findall(r"[\d.,]+", original_price.replace(".", "").replace(",", ""))
        if nums:
            try:
                base_val      = int(nums[0])
                discounted    = int(base_val * (1 - discount_pct / 100))
                # Reformat with same prefix/suffix style
                prefix        = original_price[:original_price.index(nums[0])].rstrip()
                price_display = f"~~{original_price}~~ → **{prefix} {discounted:,}** (-{discount_pct}% vote discount 🗳️)"
            except Exception:
                price_display = f"{original_price} (-{discount_pct}% vote discount 🗳️)"
        else:
            price_display = f"{original_price} (-{discount_pct}% vote discount 🗳️)"
    else:
        price_display = original_price

    # ── Build payment detail string ───────────────────────────────────────
    if payment == "qris":
        pay_detail = pm_entry.get("info") or "Scan QRIS di bawah."
        if pm_entry.get("image_url"):
            pay_detail += f"\n[📷 Lihat QRIS]({pm_entry['image_url']})"
    elif payment == "bank":
        pay_detail = (f"**Bank:** {pm_entry.get('bank_name','-')}\n"
                      f"**No. Rekening:** `{pm_entry.get('account_number','-')}`\n"
                      f"**Atas Nama:** {pm_entry.get('account_name','-')}")
    else:  # ewallet
        pay_detail = (f"**Tipe:** {pm_entry.get('type','-')}\n"
                      f"**Nomor:** `{pm_entry.get('number','-')}`")

    # ── DM user: payment instructions + request proof ────────────────────
    proof_request = base_embed(
        "💎 Order Received — Awaiting Payment",
        f"Terima kasih sudah order **{pkg['name']}**!\n\n"
        f"**Total:** {price_display}\n"
        f"**Metode:** {payment.upper()}\n\n"
        f"{pay_detail}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📎 **Setelah bayar, kirim screenshot bukti pembayaran di sini (DM ini).**\n"
        "⏳ Bukti ditunggu selama **15 menit**. Lebih dari itu order otomatis dibatalkan.",
        color=0xF59E0B
    )

    try:
        dm_channel = await i.user.create_dm()
        await dm_channel.send(embed=proof_request)
    except discord.Forbidden:
        return await i.response.send_message(
            embed=error_embed("❌ Bot tidak bisa DM kamu.\nAktifkan DM dari server ini di Privacy Settings, lalu coba lagi."),
            ephemeral=True)

    await i.response.send_message(
        embed=success_embed("Order diterima! Cek DM kamu untuk instruksi pembayaran & kirim bukti bayar."),
        ephemeral=True)

    # ── Store pending proof entry ─────────────────────────────────────────
    pending_proofs[i.user.id] = {
        "pkg":          pkg,
        "payment":      payment,
        "pay_detail":   pay_detail,
        "guild_id":     i.guild.id,
        "guild_name":   i.guild.name,
        "user":         i.user,
        "dm_channel":   dm_channel,
        "discount_pct": discount_pct,
        "price_display": price_display,
    }

    # ── Background task: wait for proof message in DM ────────────────────
    async def wait_for_proof():
        TIMEOUT = 15 * 60  # 15 minutes

        def check(msg: discord.Message):
            return (
                msg.author.id == i.user.id
                and isinstance(msg.channel, discord.DMChannel)
                and (msg.attachments or msg.content.strip())
            )

        try:
            proof_msg: discord.Message = await bot.wait_for("message", check=check, timeout=TIMEOUT)
        except asyncio.TimeoutError:
            pending_proofs.pop(i.user.id, None)
            try:
                await dm_channel.send(embed=error_embed(
                    "⏰ Waktu habis! Order kamu dibatalkan karena bukti pembayaran tidak diterima dalam 15 menit.\n"
                    "Silakan `/premium order` lagi jika masih ingin berlangganan."))
            except Exception:
                pass
            return

        pending_proofs.pop(i.user.id, None)

        # ── Build order embed for owner ───────────────────────────────────
        order_embed = base_embed("💎 New Premium Order — Bukti Diterima",
            f"**Package:** {pkg['name']}\n"
            f"**Duration:** {pkg.get('duration','N/A')}\n"
            f"**Price:** {price_display}\n"
            f"**Payment:** {payment.upper()}\n"
            f"**Voted Discount:** {discount_pct}%\n" if discount_pct else
            f"**Package:** {pkg['name']}\n"
            f"**Duration:** {pkg.get('duration','N/A')}\n"
            f"**Price:** {price_display}\n"
            f"**Payment:** {payment.upper()}\n"
            f"**Ordered by:** {i.user.mention} (`{i.user.id}`)\n"
            f"**Server:** {i.guild.name} (`{i.guild.id}`)",
            color=0x22C55E)

        # Fix: add ordered by/server as fields so it's always shown
        order_embed.add_field(name="👤 Ordered by", value=f"{i.user.mention} (`{i.user.id}`)", inline=True)
        order_embed.add_field(name="🏠 Server", value=f"{i.guild.name} (`{i.guild.id}`)", inline=True)
        if discount_pct:
            order_embed.add_field(name="🗳️ Vote Discount", value=f"{discount_pct}%", inline=True)

        if proof_msg.content.strip():
            order_embed.add_field(name="📝 Pesan dari Buyer", value=proof_msg.content[:500], inline=False)

        owner = await bot.fetch_user(bot.owner_id)
        if owner:
            try:
                btn_view = discord.ui.View()
                btn_view.add_item(discord.ui.Button(
                    label="Contact Buyer",
                    url=f"https://discord.com/users/{i.user.id}",
                    style=discord.ButtonStyle.link))
                await owner.send(embed=order_embed, view=btn_view)
                for att in proof_msg.attachments:
                    await owner.send(
                        content=f"📎 **Bukti pembayaran dari {i.user}:**",
                        file=await att.to_file())
            except Exception:
                pass

        try:
            await dm_channel.send(embed=success_embed(
                "✅ Bukti pembayaran kamu sudah diterima!\n"
                "Tim kami akan memverifikasi dan mengaktifkan premium sesegera mungkin.\n"
                "Terima kasih! 🙏"))
        except Exception:
            pass

    asyncio.create_task(wait_for_proof())

bot.tree.add_command(premium_slash)

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  FIX #3 — EVENT SYSTEM (LIVE COUNTDOWN)
#  Phase 1: Send embed with live Discord
#           relative timestamp countdown.
#  Phase 2: At start_time → edit embed → 🟢 LIVE
#  Phase 3: At end_time   → edit embed → 🔴 ENDED
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

event_group = app_commands.Group(name="event", description="Schedule and announce events with a live countdown.")

@event_group.command(name="channel", description="Set the channel where event announcements will be posted. Requires Manage Server.")
@app_commands.describe(
    channel="The text channel to use for event announcements and countdowns"
)
async def slash_event_channel(i: discord.Interaction, channel: discord.TextChannel):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    guild_cfg(cfg, i.guild.id)["announce_channel"] = channel.id
    save_config(cfg)
    await i.response.send_message(embed=success_embed(f"Announce channel set to {channel.mention}!"))

@event_group.command(name="create", description="Schedule an event with a live countdown → auto-updates to LIVE → ENDED.")
@app_commands.describe(
    title="Event title shown in the announcement embed (e.g. 'Community Game Night')",
    name="Short event name or topic (e.g. 'Among Us Tournament')",
    start_time="Start time in WIB — format: DD/MM/YYYY HH:MM (e.g. 25/12/2025 20:00)",
    duration="How long the event runs — e.g. 1h, 30m, 1h30m, 2h"
)
async def slash_event_create(
    i: discord.Interaction,
    title: str,
    name: str,
    start_time: str,
    duration: str
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)

    gc = guild_cfg(cfg, i.guild.id)
    ch_id = gc.get("announce_channel")
    if not ch_id:
        return await i.response.send_message(
            embed=error_embed("Set announce channel first with `/event channel`."), ephemeral=True)

    announce_ch = i.guild.get_channel(ch_id)
    if not announce_ch:
        return await i.response.send_message(embed=error_embed("Announce channel not found."), ephemeral=True)

    # Parse time
    try:
        dt_naive = datetime.datetime.strptime(start_time.strip(), "%d/%m/%Y %H:%M")
        dt_wib   = WIB.localize(dt_naive)
    except ValueError:
        return await i.response.send_message(
            embed=error_embed("Invalid format. Use: `DD/MM/YYYY HH:MM`  e.g. `25/12/2025 20:00`"), ephemeral=True)

    dur_secs = parse_duration(duration)
    if dur_secs is None:
        return await i.response.send_message(
            embed=error_embed("Invalid duration. Use: `1h`, `30m`, `1h30m`"), ephemeral=True)

    dt_utc  = dt_wib.astimezone(pytz.utc).replace(tzinfo=datetime.timezone.utc)
    end_utc = dt_utc + datetime.timedelta(seconds=dur_secs)

    # ── Phase 1: SCHEDULED embed (countdown) ──
    def make_scheduled_embed() -> discord.Embed:
        embed = base_embed(f"📅 {title}", f"**{name}**", color=0xF59E0B)
        embed.add_field(name="📌 Status",      value="⏳ **Scheduled**",                         inline=True)
        embed.add_field(name="🕐 Start (WIB)", value=dt_wib.strftime("%d %b %Y — %H:%M WIB"),   inline=True)
        embed.add_field(name="⏱️ Duration",    value=fmt_duration(dur_secs),                     inline=True)
        embed.add_field(name="⏰ Starts",      value=discord.utils.format_dt(dt_utc, "R"),       inline=False)
        embed.set_footer(text="JoyCannot Event System • Status auto-updates")
        return embed

    # ── Phase 2: LIVE embed ────────────────────
    def make_live_embed() -> discord.Embed:
        embed = base_embed(f"🟢 {title} — LIVE NOW!", f"**{name}**", color=0x22C55E)
        embed.add_field(name="📌 Status",      value="🟢 **LIVE**",                              inline=True)
        embed.add_field(name="🕐 Started",     value=dt_wib.strftime("%d %b %Y — %H:%M WIB"),   inline=True)
        embed.add_field(name="⏱️ Duration",    value=fmt_duration(dur_secs),                     inline=True)
        embed.add_field(name="🏁 Ends",        value=discord.utils.format_dt(end_utc, "R"),      inline=False)
        embed.set_footer(text="JoyCannot Event System • Event is live!")
        return embed

    # ── Phase 3: ENDED embed ───────────────────
    def make_ended_embed() -> discord.Embed:
        embed = base_embed(f"🔴 {title} — Ended", f"**{name}**", color=0xEF4444)
        embed.add_field(name="📌 Status",      value="🔴 **Ended**",                             inline=True)
        embed.add_field(name="🕐 Started",     value=dt_wib.strftime("%d %b %Y — %H:%M WIB"),   inline=True)
        embed.add_field(name="⏱️ Duration",    value=fmt_duration(dur_secs),                     inline=True)
        embed.add_field(name="✅ Finished at",  value=discord.utils.format_dt(end_utc, "f"),     inline=False)
        embed.set_footer(text="JoyCannot Event System • This event has ended.")
        return embed

    # Send Phase 1
    msg = await announce_ch.send("@everyone", embed=make_scheduled_embed())
    await i.response.send_message(
        embed=success_embed(f"Event scheduled and announced in {announce_ch.mention}!"), ephemeral=True)

    # Schedule the phase transitions
    async def event_lifecycle():
        now_utc = discord.utils.utcnow()

        # Wait until start
        wait_start = (dt_utc - now_utc).total_seconds()
        if wait_start > 0:
            # 5-min reminder
            if wait_start > 330:
                await asyncio.sleep(wait_start - 300)
                try:
                    remind = base_embed(f"⏰ Starting in 5 minutes — {title}",
                        f"**{name}** begins {discord.utils.format_dt(dt_utc, 'R')}!", color=0xF59E0B)
                    await announce_ch.send("@everyone", embed=remind)
                except Exception:
                    pass
                # Wait remaining 5 min
                await asyncio.sleep(min(300, (dt_utc - discord.utils.utcnow()).total_seconds()))
            else:
                await asyncio.sleep(max(0, wait_start))

        # Phase 2: LIVE
        try:
            await msg.edit(embed=make_live_embed())
            await announce_ch.send("@everyone", embed=base_embed(
                f"🟢 {title} is now LIVE!", f"**{name}** has started!", color=0x22C55E))
        except Exception:
            pass

        # Wait duration
        await asyncio.sleep(dur_secs)

        # Phase 3: ENDED
        try:
            await msg.edit(embed=make_ended_embed())
            await announce_ch.send(embed=base_embed(
                f"🔴 {title} has ended.", f"Thank you for joining **{name}**!", color=0xEF4444))
        except Exception:
            pass

    asyncio.create_task(event_lifecycle())

bot.tree.add_command(event_group)

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  FIX #2 — PREFIX BRIDGE FOR SLASH COMMANDS
#  These mirror every slash command so users
#  can also type e.g. "!Joy kick @user"
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

@bot.command(name="kick")
async def pfx_kick(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    await do_kick(ctx.guild, ctx.author, member, reason, ctx.send)

@bot.command(name="ban")
async def pfx_ban(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    await do_ban(ctx.guild, ctx.author, member, reason, ctx.send)

@bot.command(name="timeout")
async def pfx_timeout(ctx, member: discord.Member, minutes: int, *, reason: str = "No reason provided."):
    await do_timeout(ctx.guild, ctx.author, member, minutes, reason, ctx.send)

@bot.command(name="warn")
async def pfx_warn(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    await do_warn(ctx.guild, ctx.author, member, reason, ctx.send)

@bot.command(name="addrole")
async def pfx_addrole(ctx, member: discord.Member, role: discord.Role):
    await do_addrole(ctx.guild, ctx.author, member, role, ctx.send)

@bot.command(name="removerole")
async def pfx_removerole(ctx, member: discord.Member, role: discord.Role):
    await do_removerole(ctx.guild, ctx.author, member, role, ctx.send)

@bot.command(name="move")
async def pfx_move(ctx, member: discord.Member, channel: discord.VoiceChannel):
    await do_move(ctx.guild, ctx.author, member, channel, ctx.send)

@bot.command(name="userinfo")
async def pfx_userinfo(ctx, member: discord.Member = None):
    await do_userinfo(ctx.guild, member or ctx.author, ctx.send)

@bot.command(name="avatar")
async def pfx_avatar(ctx, member: discord.Member = None):
    await do_avatar(member or ctx.author, ctx.send)

@bot.command(name="ping")
async def pfx_ping(ctx):
    await do_ping(ctx.send)

@bot.command(name="help")
async def pfx_help(ctx):
    await do_help(ctx.send)

@bot.command(name="addemoji")
async def pfx_addemoji(ctx, emoji_or_url: str = "", *, name: str = ""):
    """
    !Joy addemoji <:emoji:id>           → copy emoji from another server
    !Joy addemoji <:emoji:id> newname   → copy with custom name
    !Joy addemoji <url> <name>          → add from image URL
    """
    if not ctx.author.guild_permissions.manage_emojis:
        return await ctx.send(embed=error_embed(t(cfg, ctx.guild.id, "no_perm")))
    if not emoji_or_url:
        return await ctx.send(embed=error_embed(
            "**Usage:**\n"
            "`!Joy addemoji <:emoji:id>` — paste emoji from another server\n"
            "`!Joy addemoji <:emoji:id> customname` — paste with custom name\n"
            "`!Joy addemoji <url> <name>` — add from image URL"))
    result = await do_addemoji(ctx.guild, emoji_or_url, name)
    if result["success"]:
        emoji = result["emoji"]
        await ctx.send(embed=success_embed(
            t(cfg, ctx.guild.id, "emoji_add", name=emoji.name) + f" {emoji}"))
    else:
        await ctx.send(embed=error_embed(result["error"]))

# Language prefix bridge
@bot.command(name="language")
async def pfx_language(ctx, action: str = "list", lang: str = ""):
    if action == "set":
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=error_embed(t(cfg, ctx.guild.id, "no_perm")))
        if lang not in LANGUAGES:
            return await ctx.send(embed=error_embed(f"Valid codes: {', '.join(LANGUAGES.keys())}"))
        guild_cfg(cfg, ctx.guild.id)["language"] = lang
        save_config(cfg)
        await ctx.send(embed=success_embed(t(cfg, ctx.guild.id, "lang_set", lang=LANGUAGES[lang])))
    else:
        cur   = guild_cfg(cfg, ctx.guild.id).get("language", "en")
        lines = "\n".join(f"{'✅' if k==cur else '◽'} `{k}` — {v}" for k, v in LANGUAGES.items())
        await ctx.send(embed=info_embed("🌐 Supported Languages", lines))

# Event prefix bridge
@bot.command(name="event")
async def pfx_event(ctx, action: str = "", *, args: str = ""):
    if action == "channel":
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=error_embed(t(cfg, ctx.guild.id, "no_perm")))
        if not ctx.message.channel_mentions:
            return await ctx.send(embed=error_embed("Usage: `!Joy event channel #channel`"))
        ch = ctx.message.channel_mentions[0]
        guild_cfg(cfg, ctx.guild.id)["announce_channel"] = ch.id
        save_config(cfg)
        await ctx.send(embed=success_embed(f"Announce channel set to {ch.mention}!"))
    elif action == "create":
        await ctx.send(embed=info_embed("💡 Tip",
            "Use `/event create` for the full event creator with all fields properly labeled."))
    else:
        await ctx.send(embed=error_embed("Actions: `channel`, `create`"))

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  FIX #1 — PREMIUM SETUP (EMBED + BUTTONS)
#  Owner uses "!Joy premium" → interactive
#  embed UI with buttons to manage packages
#  and payment methods.
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

def is_owner():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id == bot.owner_id
    return commands.check(predicate)


def build_premium_embed() -> discord.Embed:
    packages = cfg.get("premium_packages", [])
    pm       = cfg.get("payment_methods", {})
    pc       = cfg.get("premium_commands", [])
    pu       = cfg.get("premium_users", [])
    pg       = cfg.get("premium_guilds", [])

    embed = base_embed("💎 Premium Package Manager",
        "Manage packages, payment methods, command locks, and premium users below.")

    # ── Packages ──
    if packages:
        pkg_lines = "\n".join(
            f"**{idx+1}.** `{p['name']}` — {p['duration']} — {p['type']} — {p['price']}"
            for idx, p in enumerate(packages)
        )
    else:
        pkg_lines = "*No packages yet.*"
    embed.add_field(name="📦 Packages", value=pkg_lines, inline=False)

    # ── Payment Methods (with details) ──
    pay_lines = []
    for key, data in pm.items():
        if not isinstance(data, dict):
            continue
        status = "✅" if data.get("enabled") else "❌"
        if key == "qris":
            detail = data.get("info") or data.get("image_url") or "*(no detail set)*"
            pay_lines.append(f"{status} **QRIS** — {detail[:60]}")
        elif key == "bank":
            bn  = data.get("bank_name") or "-"
            an  = data.get("account_number") or "-"
            anm = data.get("account_name") or "-"
            pay_lines.append(f"{status} **Bank** — {bn} · `{an}` a/n {anm}")
        elif key == "ewallet":
            etype = data.get("type") or "-"
            num   = data.get("number") or "-"
            pay_lines.append(f"{status} **E-Wallet** ({etype}) — `{num}`")
    embed.add_field(name="💳 Payment Methods", value="\n".join(pay_lines) or "*(none)*", inline=False)

    # ── Premium-locked commands ──
    embed.add_field(
        name="🔒 Premium-Locked Commands",
        value=", ".join(f"`{c}`" for c in pc) if pc else "*(none locked)*",
        inline=False
    )

    # ── Premium users ──
    embed.add_field(
        name="👑 Premium Users",
        value=", ".join(f"`{uid}`" for uid in pu[:10]) + ("…" if len(pu) > 10 else "") if pu else "*(none)*",
        inline=False
    )

    # ── Premium guilds (nickname activated) ──
    if pg:
        guild_lines = []
        for gid in pg[:10]:
            g = bot.get_guild(gid)
            guild_lines.append(f"✅ **{g.name}** (`{gid}`)" if g else f"✅ `{gid}` *(offline)*")
        guild_lines_str = "\n".join(guild_lines) + ("…" if len(pg) > 10 else "")
    else:
        guild_lines_str = "*(none activated)*"
    embed.add_field(name="🏷️ Premium Guilds (Nickname Active)", value=guild_lines_str, inline=False)

    # ── Vote discount config ──
    discount   = cfg.get("vote_discount", 10)
    has_secret = "✅ Set" if cfg.get("topgg_webhook_secret") else "❌ Not set"
    embed.add_field(
        name="🗳️ Vote Settings",
        value=f"**Discount:** {discount}%  |  **Webhook Secret:** {has_secret}",
        inline=False
    )

    # ── Avatar config ──
    av_def  = cfg.get("avatar_default", "")
    av_prem = cfg.get("avatar_premium", "")
    embed.add_field(
        name="🖼️ Bot Avatars",
        value=(
            f"**Default:** {'✅ Set' if av_def else '❌ Not set'}\n"
            f"**Premium:** {'✅ Set' if av_prem else '❌ Not set'}\n"
            f"**Current state:** {'🟡 Premium avatar active' if cfg.get('premium_guilds') else '⚪ Default avatar active'}"
        ),
        inline=False
    )

    return embed


class PremiumManagerView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    def check_owner(self, i: discord.Interaction) -> bool:
        return i.user.id == self.owner_id

    # ── ROW 0: Package management ─────────────────────────────
    @discord.ui.button(label="➕ Add Package", style=discord.ButtonStyle.success, row=0)
    async def add_package(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(AddPackageModal())

    @discord.ui.button(label="🗑️ Remove Package", style=discord.ButtonStyle.danger, row=0)
    async def remove_package(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        packages = cfg.get("premium_packages", [])
        if not packages:
            return await i.response.send_message(embed=error_embed("No packages to remove."), ephemeral=True)
        await i.response.send_modal(RemovePackageModal())

    # ── ROW 1: Toggle payment methods ────────────────────────
    @discord.ui.button(label="QRIS 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_qris(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        pm = cfg["payment_methods"]["qris"]
        pm["enabled"] = not pm.get("enabled", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    @discord.ui.button(label="Bank 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_bank(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        pm = cfg["payment_methods"]["bank"]
        pm["enabled"] = not pm.get("enabled", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    @discord.ui.button(label="E-Wallet 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_ewallet(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        pm = cfg["payment_methods"]["ewallet"]
        pm["enabled"] = not pm.get("enabled", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    # ── ROW 2: Set payment details ────────────────────────────
    @discord.ui.button(label="📷 Set QRIS", style=discord.ButtonStyle.primary, row=2)
    async def set_qris(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(SetQRISModal())

    @discord.ui.button(label="🏦 Set Bank", style=discord.ButtonStyle.primary, row=2)
    async def set_bank(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(SetBankModal())

    @discord.ui.button(label="📱 Set E-Wallet", style=discord.ButtonStyle.primary, row=2)
    async def set_ewallet(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(SetEWalletModal())

    # ── ROW 3: Command lock + premium users ───────────────────
    @discord.ui.button(label="🔒 Lock Command", style=discord.ButtonStyle.danger, row=3)
    async def lock_command(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(LockCommandModal())

    @discord.ui.button(label="🔓 Unlock Command", style=discord.ButtonStyle.success, row=3)
    async def unlock_command(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(UnlockCommandModal())

    @discord.ui.button(label="👤 Add Premium User", style=discord.ButtonStyle.secondary, row=3)
    async def add_premium_user(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(AddPremiumUserModal())

    # ── ROW 4: Guild premium nickname ─────────────────────────
    @discord.ui.button(label="🏷️ Activate Guild", style=discord.ButtonStyle.success, row=4)
    async def activate_guild(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(GuildNickModal(activate=True))

    @discord.ui.button(label="🗑️ Deactivate Guild", style=discord.ButtonStyle.danger, row=4)
    async def deactivate_guild(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(GuildNickModal(activate=False))

    @discord.ui.button(label="🔃 Refresh", style=discord.ButtonStyle.primary, row=4)
    async def refresh(self, i: discord.Interaction, _btn: discord.ui.Button):
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    # ── ROW 5: Vote settings ──────────────────────────────────────────────
    @discord.ui.button(label="🗳️ Set Vote Discount", style=discord.ButtonStyle.secondary, row=4)
    async def set_vote_discount(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(VoteSettingsModal())

    @discord.ui.button(label="🖼️ Set Avatars", style=discord.ButtonStyle.secondary, row=4)
    async def set_avatars(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(SetAvatarsModal())


class AddPackageModal(discord.ui.Modal, title="➕ Add Premium Package"):
    pkg_name = discord.ui.TextInput(label="Package Name",        placeholder="e.g. Gold",          max_length=50)
    duration = discord.ui.TextInput(label="Duration",            placeholder="e.g. 30 days",       max_length=30)
    pkg_type = discord.ui.TextInput(label="Type",                placeholder="basic / premium / vip", max_length=20)
    price    = discord.ui.TextInput(label="Price",               placeholder="e.g. Rp 50.000",     max_length=30)

    async def on_submit(self, i: discord.Interaction):
        cfg.setdefault("premium_packages", []).append({
            "name":     self.pkg_name.value,
            "duration": self.duration.value,
            "type":     self.pkg_type.value,
            "price":    self.price.value,
        })
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class RemovePackageModal(discord.ui.Modal, title="🗑️ Remove Premium Package"):
    pkg_name = discord.ui.TextInput(label="Package Name to Remove", placeholder="Exact name", max_length=50)

    async def on_submit(self, i: discord.Interaction):
        before = len(cfg.get("premium_packages", []))
        cfg["premium_packages"] = [
            p for p in cfg.get("premium_packages", [])
            if p["name"].lower() != self.pkg_name.value.strip().lower()
        ]
        save_config(cfg)
        removed = before - len(cfg["premium_packages"])
        if removed:
            await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))
        else:
            await i.response.send_message(
                embed=error_embed(f"Package `{self.pkg_name.value}` not found."), ephemeral=True)


# ── Payment detail modals ─────────────────────────────────────────────────

class SetQRISModal(discord.ui.Modal, title="📷 Set QRIS Details"):
    image_url = discord.ui.TextInput(
        label="QRIS Image URL", placeholder="https://... (link to QR image)", max_length=300, required=False)
    info = discord.ui.TextInput(
        label="Info / Description", placeholder="e.g. Scan QR → confirm Rp amount",
        max_length=100, required=False)

    async def on_submit(self, i: discord.Interaction):
        cfg["payment_methods"]["qris"]["image_url"] = self.image_url.value.strip()
        cfg["payment_methods"]["qris"]["info"]      = self.info.value.strip()
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class SetBankModal(discord.ui.Modal, title="🏦 Set Bank Transfer Details"):
    bank_name      = discord.ui.TextInput(label="Nama Bank",      placeholder="e.g. BCA / Mandiri", max_length=50)
    account_number = discord.ui.TextInput(label="Nomor Rekening", placeholder="e.g. 1234567890",   max_length=30)
    account_name   = discord.ui.TextInput(label="Atas Nama",      placeholder="e.g. John Doe",     max_length=60)

    async def on_submit(self, i: discord.Interaction):
        cfg["payment_methods"]["bank"]["bank_name"]      = self.bank_name.value.strip()
        cfg["payment_methods"]["bank"]["account_number"] = self.account_number.value.strip()
        cfg["payment_methods"]["bank"]["account_name"]   = self.account_name.value.strip()
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class SetEWalletModal(discord.ui.Modal, title="📱 Set E-Wallet Details"):
    etype  = discord.ui.TextInput(label="Tipe E-Wallet", placeholder="e.g. GoPay / OVO / Dana / ShopeePay", max_length=50)
    number = discord.ui.TextInput(label="Nomor",         placeholder="e.g. 08123456789",                    max_length=30)

    async def on_submit(self, i: discord.Interaction):
        cfg["payment_methods"]["ewallet"]["type"]   = self.etype.value.strip()
        cfg["payment_methods"]["ewallet"]["number"] = self.number.value.strip()
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


# ── Command lock modals ───────────────────────────────────────────────────

class LockCommandModal(discord.ui.Modal, title="🔒 Lock Command (Premium Only)"):
    cmd_name = discord.ui.TextInput(
        label="Command Name",
        placeholder="e.g. kick  OR  ticket setup  OR  event create",
        max_length=60
    )

    async def on_submit(self, i: discord.Interaction):
        name = self.cmd_name.value.strip().lower()
        pc   = cfg.setdefault("premium_commands", [])
        if name in pc:
            await i.response.send_message(
                embed=error_embed(f"`{name}` is already premium-locked."), ephemeral=True)
            return
        pc.append(name)
        save_config(cfg)
        # Re-sync slash commands to show 💎 label
        asyncio.create_task(apply_premium_labels())
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class UnlockCommandModal(discord.ui.Modal, title="🔓 Unlock Command"):
    cmd_name = discord.ui.TextInput(
        label="Command Name to Unlock",
        placeholder="Exact name as shown in Premium-Locked list",
        max_length=60
    )

    async def on_submit(self, i: discord.Interaction):
        name = self.cmd_name.value.strip().lower()
        pc   = cfg.get("premium_commands", [])
        if name not in pc:
            await i.response.send_message(
                embed=error_embed(f"`{name}` is not premium-locked."), ephemeral=True)
            return
        cfg["premium_commands"] = [c for c in pc if c != name]
        save_config(cfg)
        asyncio.create_task(apply_premium_labels())
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class AddPremiumUserModal(discord.ui.Modal, title="👤 Add / Remove Premium User"):
    user_id  = discord.ui.TextInput(label="User ID",      placeholder="Discord user ID (numbers only)", max_length=20)
    action   = discord.ui.TextInput(label="Action",       placeholder="add  OR  remove",                max_length=6)

    async def on_submit(self, i: discord.Interaction):
        try:
            uid = int(self.user_id.value.strip())
        except ValueError:
            return await i.response.send_message(embed=error_embed("Invalid user ID."), ephemeral=True)
        act = self.action.value.strip().lower()
        pu  = cfg.setdefault("premium_users", [])
        if act == "add":
            if uid in pu:
                return await i.response.send_message(embed=error_embed("User already has premium."), ephemeral=True)
            pu.append(uid)
            save_config(cfg)
            await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))
        elif act == "remove":
            if uid not in pu:
                return await i.response.send_message(embed=error_embed("User not in premium list."), ephemeral=True)
            cfg["premium_users"] = [u for u in pu if u != uid]
            save_config(cfg)
            await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))
        else:
            await i.response.send_message(embed=error_embed("Action must be `add` or `remove`."), ephemeral=True)


class GuildNickModal(discord.ui.Modal):
    """Activate or deactivate 'JoyCannot Premium' nickname in a specific guild."""

    guild_id_input = discord.ui.TextInput(
        label="Guild ID",
        placeholder="Right-click server → Copy Server ID",
        max_length=20
    )

    def __init__(self, activate: bool):
        action_label = "Activate" if activate else "Deactivate"
        super().__init__(title=f"🏷️ {action_label} Premium Nickname")
        self.activate = activate

    async def on_submit(self, i: discord.Interaction):
        try:
            gid = int(self.guild_id_input.value.strip())
        except ValueError:
            return await i.response.send_message(embed=error_embed("Invalid Guild ID."), ephemeral=True)

        guild = bot.get_guild(gid)
        if not guild:
            return await i.response.send_message(
                embed=error_embed(f"Bot is not in guild `{gid}` or guild not found."), ephemeral=True)

        pg = cfg.setdefault("premium_guilds", [])

        if self.activate:
            if gid in pg:
                return await i.response.send_message(
                    embed=error_embed(f"**{guild.name}** is already activated."), ephemeral=True)
            pg.append(gid)
            save_config(cfg)
            await i.response.defer()
            await set_guild_premium_nick(guild, activate=True)

            # ── Switch to premium avatar if this is the FIRST premium guild ──
            if len(cfg.get("premium_guilds", [])) == 1:
                avatar_url = cfg.get("avatar_premium", "")
                if avatar_url:
                    await set_bot_avatar(avatar_url)

            await i.followup.send(
                embed=success_embed(
                    f"✅ Premium activated for **{guild.name}**!\n"
                    f"• Nickname → `{PREMIUM_NICK}`\n"
                    f"• Role → `{PREMIUM_ROLE_NAME}` (yellow)\n"
                    f"• Avatar → {'switched to premium 🖼️' if cfg.get('avatar_premium') else 'not set (configure via Set Avatars button)'}"),
                ephemeral=True)
            await i.edit_original_response(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))
        else:
            if gid not in pg:
                return await i.response.send_message(
                    embed=error_embed(f"**{guild.name}** is not in the premium list."), ephemeral=True)
            cfg["premium_guilds"] = [g for g in pg if g != gid]
            save_config(cfg)
            await i.response.defer()
            await set_guild_premium_nick(guild, activate=False)

            # ── Revert to default avatar if NO premium guilds remain ──────
            if len(cfg.get("premium_guilds", [])) == 0:
                avatar_url = cfg.get("avatar_default", "")
                if avatar_url:
                    await set_bot_avatar(avatar_url)

            await i.followup.send(
                embed=success_embed(
                    f"✅ Premium deactivated for **{guild.name}**.\n"
                    f"• Nickname reset\n"
                    f"• Role removed\n"
                    f"• Avatar → {'reverted to default 🖼️' if cfg.get('avatar_default') else 'not set'}"),
                ephemeral=True)
            await i.edit_original_response(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))



class SetAvatarsModal(discord.ui.Modal, title="🖼️ Set Bot Avatars"):
    default_url = discord.ui.TextInput(
        label="Default Avatar URL",
        placeholder="Image URL shown when NO server has premium active",
        max_length=300,
        required=False
    )
    premium_url = discord.ui.TextInput(
        label="Premium Avatar URL",
        placeholder="Image URL shown when at least 1 server has premium active",
        max_length=300,
        required=False
    )

    async def on_submit(self, i: discord.Interaction):
        default = self.default_url.value.strip()
        premium = self.premium_url.value.strip()

        updated = []
        if default:
            cfg["avatar_default"] = default
            updated.append("Default avatar saved")
        if premium:
            cfg["avatar_premium"] = premium
            updated.append("Premium avatar saved")

        if not updated:
            return await i.response.send_message(
                embed=error_embed("No URLs provided. Fill in at least one field."), ephemeral=True)

        save_config(cfg)

        # ── Apply immediately based on current premium state ──────────────
        await i.response.defer()
        has_premium = len(cfg.get("premium_guilds", [])) > 0
        if has_premium and premium:
            ok = await set_bot_avatar(premium)
            updated.append(f"Premium avatar {'applied ✅' if ok else 'failed to apply ❌'}")
        elif not has_premium and default:
            ok = await set_bot_avatar(default)
            updated.append(f"Default avatar {'applied ✅' if ok else 'failed to apply ❌'}")

        await i.followup.send(
            embed=success_embed("\n".join(f"• {u}" for u in updated)),
            ephemeral=True)
        await i.edit_original_response(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


class VoteSettingsModal(discord.ui.Modal, title="🗳️ Vote Discount Settings"):
    discount_input = discord.ui.TextInput(
        label="Discount % for voters",
        placeholder="e.g. 10  (means 10% off — enter 0 to disable)",
        max_length=3
    )
    webhook_secret = discord.ui.TextInput(
        label="top.gg Webhook Secret",
        placeholder="Secret token from top.gg webhook settings",
        max_length=100,
        required=False
    )

    async def on_submit(self, i: discord.Interaction):
        try:
            pct = int(self.discount_input.value.strip())
            if not (0 <= pct <= 100):
                raise ValueError
        except ValueError:
            return await i.response.send_message(
                embed=error_embed("Discount must be a number between 0 and 100."), ephemeral=True)
        cfg["vote_discount"] = pct
        secret = self.webhook_secret.value.strip()
        if secret:
            cfg["topgg_webhook_secret"] = secret
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


@bot.command(name="premium")
@is_owner()
async def pfx_premium(ctx: commands.Context):
    """!Joy premium — Opens the interactive premium manager (owner only)."""
    await ctx.send(embed=build_premium_embed(), view=PremiumManagerView(ctx.author.id))


# ─────────────────────────────────────────────
# ── MAINTENANCE BROADCAST (OWNER PREFIX)
# ─────────────────────────────────────────────

class MaintenanceBroadcastView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    def check_owner(self, i: discord.Interaction) -> bool:
        return i.user.id == self.owner_id

    @discord.ui.button(label="📝 Compose Broadcast", style=discord.ButtonStyle.primary, row=0)
    async def compose(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(MaintenanceModal(self.owner_id))

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.edit_message(
            embed=info_embed("🚫 Cancelled", "Maintenance broadcast manager closed."), view=None)


class MaintenanceModal(discord.ui.Modal, title="📢 Compose Maintenance Broadcast"):
    def __init__(self, owner_id: int):
        super().__init__()
        self.owner_id = owner_id

    title_input = discord.ui.TextInput(
        label="Title", placeholder="e.g. Scheduled Maintenance",
        max_length=100, default="🔧 Maintenance Notice")
    description = discord.ui.TextInput(
        label="Message", style=discord.TextStyle.paragraph,
        placeholder="Describe the maintenance...", max_length=1000,
        default="The bot is undergoing scheduled maintenance.")
    btn_label = discord.ui.TextInput(
        label="Button Label", placeholder="e.g. Status Page",
        max_length=50, default="Status Page", required=False)
    btn_url = discord.ui.TextInput(
        label="Button URL", placeholder="https://status.joycannot.xyz",
        max_length=200, default="https://status.joycannot.xyz", required=False)

    async def on_submit(self, i: discord.Interaction):
        preview = base_embed(f"📢 {self.title_input.value}", self.description.value, color=0xF59E0B)
        preview.add_field(name="📊 Target Servers", value=str(len(bot.guilds)), inline=True)
        preview.add_field(name="🔘 Button", value=self.btn_label.value or "Status Page", inline=True)
        preview.set_footer(text="Preview — confirm below to broadcast")

        view = MaintenanceConfirmView(
            title      = self.title_input.value,
            description= self.description.value,
            btn_label  = self.btn_label.value or "Status Page",
            btn_url    = self.btn_url.value   or "https://status.joycannot.xyz",
            owner_id   = self.owner_id,
        )
        await i.response.send_message(embed=preview, view=view, ephemeral=False)


class MaintenanceConfirmView(discord.ui.View):
    def __init__(self, title: str, description: str, btn_label: str, btn_url: str, owner_id: int):
        super().__init__(timeout=120)
        self.title       = title
        self.description = description
        self.btn_label   = btn_label
        self.btn_url     = btn_url
        self.owner_id    = owner_id

    @discord.ui.button(label="✅ Broadcast Now", style=discord.ButtonStyle.success, row=0)
    async def confirm(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.edit_message(
            embed=info_embed("📤 Broadcasting...", f"Sending to **{len(bot.guilds)}** servers..."),
            view=None)

        broadcast_embed = base_embed(f"📢 {self.title}", self.description, color=0xF59E0B)
        broadcast_embed.add_field(name="Sent by", value=str(i.user), inline=True)
        broadcast_embed.add_field(name="Time",
            value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=True)

        btn_view = discord.ui.View()
        if self.btn_url.startswith("http"):
            btn_view.add_item(discord.ui.Button(
                label=self.btn_label, url=self.btn_url, style=discord.ButtonStyle.link))

        ok, fail = 0, 0
        for guild in bot.guilds:
            gc = guild_cfg(cfg, guild.id)
            ch = guild.get_channel(gc.get("main_channel") or 0)
            if not ch:
                ch = guild.system_channel
            if not ch:
                for c in guild.text_channels:
                    if c.permissions_for(guild.me).send_messages:
                        ch = c
                        break
            if ch:
                try:
                    await ch.send(embed=broadcast_embed, view=btn_view)
                    ok += 1
                except Exception:
                    fail += 1
            else:
                fail += 1
            await asyncio.sleep(0.5)

        result = success_embed(f"Broadcast complete!\n✅ Success: **{ok}** | ❌ Failed: **{fail}**")
        await i.edit_original_response(embed=result)

    @discord.ui.button(label="✏️ Edit", style=discord.ButtonStyle.secondary, row=0)
    async def edit(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(MaintenanceModal(self.owner_id))

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.edit_message(embed=info_embed("🚫 Cancelled", "Broadcast cancelled."), view=None)


@bot.command(name="maintenance")
@is_owner()
async def pfx_maintenance(ctx: commands.Context):
    """!Joy maintenance — Opens the interactive Maintenance Broadcast manager (owner only)."""
    embed = base_embed("📢 Maintenance Broadcast Manager",
        "Use the button below to compose and preview your maintenance message "
        "before broadcasting it to all servers.")
    embed.add_field(name="📊 Connected Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="📌 Note",
        value="The message will be sent to the configured `main_channel` of each server.", inline=False)
    await ctx.send(embed=embed, view=MaintenanceBroadcastView(ctx.author.id))


class SetChannelModal(discord.ui.Modal, title="📌 Set Main Channel"):
    guild_id_input   = discord.ui.TextInput(label="Guild ID",   placeholder="Right-click server → Copy ID", max_length=20)
    channel_id_input = discord.ui.TextInput(label="Channel ID", placeholder="Right-click channel → Copy ID", max_length=20)

    async def on_submit(self, i: discord.Interaction):
        try:
            gid = int(self.guild_id_input.value.strip())
            cid = int(self.channel_id_input.value.strip())
        except ValueError:
            return await i.response.send_message(embed=error_embed("Both IDs must be valid numbers."), ephemeral=True)
        guild_cfg(cfg, gid)["main_channel"] = cid
        save_config(cfg)
        guild_obj = bot.get_guild(gid)
        guild_name = guild_obj.name if guild_obj else f"ID `{gid}`"
        ch_obj = bot.get_channel(cid)
        ch_name = ch_obj.mention if ch_obj else f"ID `{cid}`"
        result = base_embed("📌 Main Channel Set",
            f"**Server:** {guild_name}\n**Channel:** {ch_name}")
        await i.response.edit_message(embed=result, view=None)


class SetChannelView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="📌 Set Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_channel(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(SetChannelModal())

    @discord.ui.button(label="📋 List Servers", style=discord.ButtonStyle.secondary, row=0)
    async def list_servers(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        lines = []
        for g in bot.guilds[:20]:
            gc      = guild_cfg(cfg, g.id)
            main_ch = g.get_channel(gc.get("main_channel") or 0)
            ch_str  = main_ch.mention if main_ch else "*(not set)*"
            lines.append(f"**{g.name}** (`{g.id}`) → {ch_str}")
        embed = base_embed("📋 Server Main Channels",
            "\n".join(lines) or "No servers." +
            (f"\n\n*Showing first 20 of {len(bot.guilds)}*" if len(bot.guilds) > 20 else ""))
        await i.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, row=0)
    async def close(self, i: discord.Interaction, _btn: discord.ui.Button):
        if i.user.id != self.owner_id:
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.edit_message(embed=info_embed("🚫 Closed", "SetChannel manager closed."), view=None)


@bot.command(name="setchannel")
@is_owner()
async def pfx_setchannel(ctx: commands.Context):
    """!Joy setchannel — Opens the interactive Set Channel manager (owner only)."""
    embed = base_embed("📌 Set Main Channel",
        "Set the main notification channel for any server the bot is in.\n"
        "Click **Set Channel** and enter the Guild ID and Channel ID.")
    embed.add_field(name="💡 Tip", value="Enable Developer Mode in Discord settings to copy IDs.", inline=False)
    embed.add_field(name="📊 Connected Servers", value=str(len(bot.guilds)), inline=True)
    await ctx.send(embed=embed, view=SetChannelView(ctx.author.id))


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@bot.tree.error
async def on_app_command_error(i: discord.Interaction, error: app_commands.AppCommandError):
    msg = (
        t(cfg, i.guild.id if i.guild else 0, "no_perm") if isinstance(error, app_commands.MissingPermissions)
        else f"⏱️ Slow down! Retry in {error.retry_after:.1f}s." if isinstance(error, app_commands.CommandOnCooldown)
        else f"Unexpected error: `{error}`"
    )
    try:
        await i.response.send_message(embed=error_embed(msg), ephemeral=True)
    except Exception:
        await i.followup.send(embed=error_embed(msg), ephemeral=True)

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        cmd_name = ctx.command.qualified_name if ctx.command else None
        if cmd_name and is_premium_command(cmd_name):
            await ctx.send(embed=base_embed(
                "💎 Premium Required",
                f"The command `{cmd_name}` is only available for **Premium** servers or users.\n\n"
                "📦 Use `/premium info` to see available packages.\n"
                "📩 Use `/premium order` to subscribe.",
                color=0xF59E0B))
        else:
            await ctx.send(embed=error_embed("❌ Owner only command."))
    elif isinstance(error, commands.CommandNotFound):
        pass  # Silently ignore unknown cmds
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=error_embed(f"Missing argument: `{error.param.name}`\nUse `!Joy help` for usage."))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=error_embed(f"Invalid argument: {error}\nUse `!Joy help` for usage."))

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  TOP.GG VOTE SYSTEM
#  - Webhook server receives vote events
#  - Stores vote timestamp per user
#  - /premium order checks vote → applies discount
#  - Discount % configurable by owner
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

TOPGG_WEBHOOK_PORT = int(os.getenv("PORT") or os.getenv("TOPGG_WEBHOOK_PORT") or "5000")
VOTE_COOLDOWN_HOURS = 12   # top.gg vote cooldown

async def start_vote_webhook():
    """Start aiohttp webhook server to receive top.gg vote events."""
    try:
        from aiohttp import web
    except ImportError:
        logging.warning("[Vote] aiohttp not installed — webhook server disabled.")
        return

    async def handle_vote(request: web.Request) -> web.Response:
        # Verify Authorization header
        secret = cfg.get("topgg_webhook_secret", "")
        if secret and request.headers.get("Authorization") != secret:
            return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Bad Request")

        user_id_str = str(data.get("user", ""))
        if not user_id_str:
            return web.Response(status=400, text="Missing user")

        # Store vote timestamp
        cfg.setdefault("votes", {})[user_id_str] = datetime.datetime.utcnow().isoformat()
        save_config(cfg)
        logging.info(f"[Vote] User {user_id_str} voted on top.gg")

        # DM the user a thank-you
        try:
            uid = int(user_id_str)
            user = await bot.fetch_user(uid)
            discount = cfg.get("vote_discount", 10)
            dm_embed = base_embed(
                "🗳️ Thanks for voting!",
                f"Thank you for voting for **JoyCannot** on top.gg! 🎉\n\n"
                f"As a reward, you get **{discount}% off** your next premium order!\n"
                f"Use `/premium order` within the next {VOTE_COOLDOWN_HOURS} hours to claim it.\n\n"
                f"[Vote again in {VOTE_COOLDOWN_HOURS}h](https://top.gg/bot/{bot.user.id}/vote)",
                color=0x22C55E
            )
            await user.send(embed=dm_embed)
        except Exception:
            pass

        return web.Response(status=200, text="OK")

    app = web.Application()
    app.router.add_post("/topgg/vote", handle_vote)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", TOPGG_WEBHOOK_PORT)
    await site.start()
    logging.info(f"[Vote] Webhook server started on port {TOPGG_WEBHOOK_PORT}")


def get_vote_discount(user_id: int) -> int:
    """Return discount % if user voted within the cooldown window, else 0."""
    votes = cfg.get("votes", {})
    ts_str = votes.get(str(user_id))
    if not ts_str:
        return 0
    try:
        voted_at = datetime.datetime.fromisoformat(ts_str)
        elapsed  = (datetime.datetime.utcnow() - voted_at).total_seconds() / 3600
        if elapsed <= VOTE_COOLDOWN_HOURS:
            return cfg.get("vote_discount", 10)
    except Exception:
        pass
    return 0


@bot.tree.command(name="vote", description="Vote for JoyCannot on top.gg and get a premium discount!")
async def slash_vote(i: discord.Interaction):
    discount     = cfg.get("vote_discount", 10)
    user_discount = get_vote_discount(i.user.id)
    bot_id       = bot.user.id
    vote_url     = f"https://top.gg/bot/{bot_id}/vote"

    if user_discount > 0:
        desc = (
            f"✅ You **already voted** and have an active **{user_discount}% discount**!\n\n"
            f"Use `/premium order` now to claim it.\n"
            f"[Vote again when cooldown expires]({vote_url})"
        )
        color = 0x22C55E
    else:
        desc = (
            f"🗳️ **Vote for JoyCannot** on top.gg and get **{discount}% off** premium!\n\n"
            f"[👉 Click here to vote]({vote_url})\n\n"
            f"After voting, use `/premium order` within {VOTE_COOLDOWN_HOURS} hours to apply the discount."
        )
        color = 0xF59E0B

    embed = base_embed("🗳️ Vote for JoyCannot", desc, color=color)
    view  = discord.ui.View()
    view.add_item(discord.ui.Button(label="Vote on top.gg", url=vote_url, style=discord.ButtonStyle.link, emoji="🗳️"))
    await i.response.send_message(embed=embed, view=view)


# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  XP / LEVELING SYSTEM  (Arcane-style)
#  + QUEST SYSTEM
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

XP_DATA_PATH   = "data/xp.json"
QUEST_DATA_PATH = "data/quests.json"

# ── XP Config ─────────────────────────────
XP_PER_MESSAGE_MIN = 15
XP_PER_MESSAGE_MAX = 25
XP_COOLDOWN_SECS   = 60   # per-user cooldown between XP gains
xp_cooldowns: dict[int, float] = {}   # uid → last_xp_time

def xp_for_level(level: int) -> int:
    """Total XP needed to reach a given level (from 0)."""
    return 5 * (level ** 2) + 50 * level + 100

def level_from_xp(total_xp: int) -> int:
    """Calculate current level from total XP."""
    level = 0
    while total_xp >= xp_for_level(level):
        total_xp -= xp_for_level(level)
        level += 1
    return level

def xp_in_current_level(total_xp: int) -> tuple[int, int]:
    """Returns (xp_into_current_level, xp_needed_for_next_level)."""
    level = 0
    while total_xp >= xp_for_level(level):
        total_xp -= xp_for_level(level)
        level += 1
    return total_xp, xp_for_level(level)

def load_xp_data() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(XP_DATA_PATH):
        return {}
    with open(XP_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_xp_data(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(XP_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user_xp(data: dict, guild_id: int, user_id: int) -> dict:
    gid = str(guild_id)
    uid = str(user_id)
    data.setdefault(gid, {})
    data[gid].setdefault(uid, {"xp": 0, "level": 0, "total_messages": 0})
    return data[gid][uid]

# ── Quest Config ───────────────────────────
# ── Default built-in quests (always present) ──
QUEST_DEFINITIONS = [
    # id, name, description, type, target, reward_xp, reward_desc, reset (daily/weekly)
    {"id": "send_5",    "name": "💬 Chatterer",       "desc": "Send 5 messages",             "type": "messages",   "target": 5,   "reward_xp": 50,  "reward": "50 XP",  "reward_type": "xp",     "reset": "daily"},
    {"id": "send_25",   "name": "🗣️ Talker",          "desc": "Send 25 messages",            "type": "messages",   "target": 25,  "reward_xp": 150, "reward": "150 XP", "reward_type": "xp",     "reset": "daily"},
    {"id": "react_3",   "name": "😄 Reactor",         "desc": "React to 3 messages",         "type": "reactions",  "target": 3,   "reward_xp": 75,  "reward": "75 XP",  "reward_type": "xp",     "reset": "daily"},
    {"id": "react_10",  "name": "🔥 Reaction Master", "desc": "React to 10 messages",        "type": "reactions",  "target": 10,  "reward_xp": 200, "reward": "200 XP", "reward_type": "xp",     "reset": "weekly"},
    {"id": "send_100",  "name": "📣 Active Member",   "desc": "Send 100 messages this week", "type": "messages",   "target": 100, "reward_xp": 500, "reward": "500 XP", "reward_type": "xp",     "reset": "weekly"},
    {"id": "help_10",   "name": "🤝 Helper",          "desc": "Reply to 10 messages",        "type": "replies",    "target": 10,  "reward_xp": 300, "reward": "300 XP", "reward_type": "xp",     "reset": "weekly"},
    {"id": "send_50",   "name": "🌟 Contributor",     "desc": "Send 50 messages this week",  "type": "messages",   "target": 50,  "reward_xp": 350, "reward": "350 XP", "reward_type": "xp",     "reset": "weekly"},
    {"id": "early_5",   "name": "🌅 Early Bird",      "desc": "Send 5 msgs before 9 AM WIB", "type": "early_msgs", "target": 5,   "reward_xp": 100, "reward": "100 XP", "reward_type": "xp",     "reset": "daily"},
]

# ─────────────────────────────────────────────
# CUSTOM QUEST + REDEEM CODE SYSTEM
# ─────────────────────────────────────────────
# Storage layout:
#   data/custom_quests.json  → per-guild custom quest definitions
#   data/redeem_codes.json   → pool of codes per quest (guild-scoped)
#   data/quests.json         → per-user progress (existing, unchanged)
#
# Custom quest reward types:
#   "xp"     → award reward_xp directly
#   "code"   → generate & DM a unique redeem code from the pool
#   "both"   → award XP AND send a code
# ─────────────────────────────────────────────

CUSTOM_QUEST_PATH = "data/custom_quests.json"
REDEEM_CODE_PATH  = "data/redeem_codes.json"

def load_custom_quests() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CUSTOM_QUEST_PATH):
        return {}
    with open(CUSTOM_QUEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_custom_quests(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(CUSTOM_QUEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_redeem_codes() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(REDEEM_CODE_PATH):
        return {}
    with open(REDEEM_CODE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_redeem_codes(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(REDEEM_CODE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_all_quests_for_guild(guild_id: int) -> list:
    """Merge built-in + custom quests for this guild."""
    custom = load_custom_quests()
    gid    = str(guild_id)
    guild_customs = custom.get(gid, [])
    return QUEST_DEFINITIONS + guild_customs

def pop_redeem_code(guild_id: int, quest_id: str) -> Optional[str]:
    """
    Pop one unused code from the pool for this quest.
    Returns the code string, or None if pool is empty.
    """
    codes = load_redeem_codes()
    gid   = str(guild_id)
    pool  = codes.get(gid, {}).get(quest_id, [])
    available = [c for c in pool if not c.get("used")]
    if not available:
        return None
    chosen = available[0]
    chosen["used"] = True
    save_redeem_codes(codes)
    return chosen["code"]

def generate_auto_code(prefix: str = "JOY") -> str:
    """Generate a random redeem code like JOY-A3X9-KZ12."""
    import random, string
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"{prefix}-{part1}-{part2}"

def load_quest_data() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(QUEST_DATA_PATH):
        return {}
    with open(QUEST_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_quest_data(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(QUEST_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_quest_period_key(reset: str) -> str:
    """Returns a period key string for daily or weekly reset tracking."""
    now = datetime.datetime.now(WIB)
    if reset == "daily":
        return now.strftime("%Y-%m-%d")
    else:  # weekly
        return now.strftime("%Y-W%W")

def get_user_quest_progress(qdata: dict, guild_id: int, user_id: int, quest_id: str, reset: str) -> dict:
    gid = str(guild_id)
    uid = str(user_id)
    period = get_quest_period_key(reset)
    qdata.setdefault(gid, {}).setdefault(uid, {}).setdefault(quest_id, {})
    entry = qdata[gid][uid][quest_id]
    # Reset if period changed
    if entry.get("period") != period:
        entry["period"]    = period
        entry["progress"]  = 0
        entry["completed"] = False
        entry["claimed"]   = False
    return entry


async def grant_quest_reward(quest: dict, member: discord.Member, guild: discord.Guild):
    """
    Grant the reward for a completed quest:
    - 'xp'   → add XP silently (caller already does this for built-ins)
    - 'code' → DM a unique redeem code from pool (or auto-generate)
    - 'both' → XP + code
    Sends a DM with reward details.
    """
    reward_type = quest.get("reward_type", "xp")
    reward_xp   = quest.get("reward_xp", 0)
    reward_desc = quest.get("reward", "XP")
    quest_name  = quest["name"]

    dm_lines = [f"**{quest_name}**\n{quest.get('desc','')}\n"]

    # ── XP reward ────────────────────────────────────────────────────────
    if reward_type in ("xp", "both") and reward_xp > 0:
        xp_data  = load_xp_data()
        user_rec = get_user_xp(xp_data, guild.id, member.id)
        old_lv   = user_rec["level"]
        user_rec["xp"] += reward_xp
        new_lv   = level_from_xp(user_rec["xp"])
        user_rec["level"] = new_lv
        save_xp_data(xp_data)
        dm_lines.append(f"⭐ **+{reward_xp} XP** awarded!")
        if new_lv > old_lv:
            gc = guild_cfg(cfg, guild.id)
            notif_ch_id = gc.get("levelup_channel") or gc.get("main_channel")
            notif_ch = guild.get_channel(notif_ch_id) if notif_ch_id else None
            if notif_ch:
                try:
                    await notif_ch.send(f"{member.mention} Mencapai Level **{new_lv}**. KELAZZZ👑!")
                except Exception:
                    pass

    # ── Code reward ───────────────────────────────────────────────────────
    if reward_type in ("code", "both"):
        code = pop_redeem_code(guild.id, quest["id"])
        if not code:
            # Auto-generate if pool is empty
            code = generate_auto_code()
        dm_lines.append(f"🎟️ **Redeem Code:** `{code}`")
        if reward_desc and reward_type == "code":
            dm_lines.append(f"🎁 Hadiah: **{reward_desc}**")
        dm_lines.append("\n📌 Gunakan kode ini sesuai instruksi dari admin server.")

    if reward_type not in ("xp", "code", "both"):
        dm_lines.append(f"🎁 Reward: **{reward_desc}**")

    try:
        await member.send(embed=base_embed(
            "🎯 Quest Completed!",
            "\n".join(dm_lines),
            color=0x22C55E
        ))
    except Exception:
        pass


# ── XP / Quest processing on message ──────────
async def process_xp_and_quests(message: discord.Message):
    """Award XP and update quest progress on every message."""
    if message.author.bot or not message.guild:
        return

    xp_data    = load_xp_data()
    quest_data = load_quest_data()
    uid        = message.author.id
    gid        = message.guild.id
    now        = discord.utils.utcnow().timestamp()

    # ── XP gain (with cooldown) ───────────────────
    last_xp = xp_cooldowns.get(uid, 0)
    if now - last_xp >= XP_COOLDOWN_SECS:
        import random
        gained_xp = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        xp_cooldowns[uid] = now

        user_rec = get_user_xp(xp_data, gid, uid)
        old_level = user_rec["level"]
        user_rec["xp"] += gained_xp
        user_rec["total_messages"] = user_rec.get("total_messages", 0) + 1
        new_level = level_from_xp(user_rec["xp"])
        user_rec["level"] = new_level
        save_xp_data(xp_data)

        # ── Level up notification ─────────────────────
        if new_level > old_level:
            gc = guild_cfg(cfg, gid)
            notif_ch_id = gc.get("levelup_channel") or gc.get("main_channel")
            notif_ch = message.guild.get_channel(notif_ch_id) if notif_ch_id else None
            if not notif_ch:
                notif_ch = message.channel
            try:
                await notif_ch.send(
                    f"{message.author.mention} Mencapai Level **{new_level}**. KELAZZZ👑!"
                )
            except Exception:
                pass

    # ── Quest progress ────────────────────────────
    now_wib    = datetime.datetime.now(WIB)
    all_quests = get_all_quests_for_guild(gid)
    for quest in all_quests:
        entry = get_user_quest_progress(quest_data, gid, uid, quest["id"], quest["reset"])
        if entry["completed"]:
            continue

        progressed = False
        if quest["type"] == "messages":
            entry["progress"] += 1
            progressed = True
        elif quest["type"] == "replies" and message.reference:
            entry["progress"] += 1
            progressed = True
        elif quest["type"] == "early_msgs" and now_wib.hour < 9:
            entry["progress"] += 1
            progressed = True

        if progressed and entry["progress"] >= quest["target"]:
            entry["completed"] = True
            entry["claimed"]   = True
            save_quest_data(quest_data)
            # Grant reward (XP + optional code) via unified function
            await grant_quest_reward(quest, message.author, message.guild)
            return  # re-save happens inside grant_quest_reward

    save_quest_data(quest_data)


async def process_reaction_quests(guild: discord.Guild, user: discord.Member):
    """Update reaction-type quests when a user adds a reaction."""
    if user.bot:
        return
    quest_data = load_quest_data()
    gid        = guild.id
    uid        = user.id
    all_quests = get_all_quests_for_guild(gid)
    for quest in all_quests:
        if quest["type"] != "reactions":
            continue
        entry = get_user_quest_progress(quest_data, gid, uid, quest["id"], quest["reset"])
        if entry["completed"]:
            continue
        entry["progress"] += 1
        if entry["progress"] >= quest["target"]:
            entry["completed"] = True
            entry["claimed"]   = True
            save_quest_data(quest_data)
            await grant_quest_reward(quest, user, guild)
            return
    save_quest_data(quest_data)


# ── Hook reaction event ────────────────────────
@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if reaction.message.guild:
        member = reaction.message.guild.get_member(user.id)
        if member:
            await process_reaction_quests(reaction.message.guild, member)


# ── /rank command ──────────────────────────────
@bot.tree.command(name="rank", description="View your current XP, level, and progress.")
@app_commands.describe(member="Member to check (leave blank for yourself)")
async def slash_rank(i: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or i.user
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, i.guild.id, target.id)
    total_xp = user_rec["xp"]
    level    = user_rec["level"]
    xp_now, xp_need = xp_in_current_level(total_xp)
    msgs     = user_rec.get("total_messages", 0)

    # Leaderboard rank
    gid = str(i.guild.id)
    guild_data = xp_data.get(gid, {})
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    rank = next((idx+1 for idx, (uid, _) in enumerate(sorted_users) if uid == str(target.id)), "?")

    # Progress bar
    filled = int((xp_now / xp_need) * 20) if xp_need > 0 else 20
    bar = "█" * filled + "░" * (20 - filled)

    embed = base_embed(f"⭐ {target.display_name}'s Rank")
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🏆 Rank",     value=f"#{rank}",               inline=True)
    embed.add_field(name="📊 Level",    value=str(level),                inline=True)
    embed.add_field(name="✉️ Messages", value=str(msgs),                  inline=True)
    embed.add_field(name="⭐ Total XP", value=str(total_xp),             inline=True)
    embed.add_field(name="📈 Progress", value=f"{xp_now}/{xp_need} XP", inline=True)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━",
                    value=f"`[{bar}]`", inline=False)
    await i.response.send_message(embed=embed)


# ── /leaderboard command ───────────────────────
@bot.tree.command(name="leaderboard", description="View the top 10 members by XP on this server.")
async def slash_leaderboard(i: discord.Interaction):
    xp_data    = load_xp_data()
    gid        = str(i.guild.id)
    guild_data = xp_data.get(gid, {})
    if not guild_data:
        return await i.response.send_message(embed=info_embed("📊 Leaderboard", "No XP data yet!"))

    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)[:10]
    lines = []
    medals = ["🥇","🥈","🥉"]
    for idx, (uid, rec) in enumerate(sorted_users):
        member = i.guild.get_member(int(uid))
        name   = member.display_name if member else f"User {uid}"
        medal  = medals[idx] if idx < 3 else f"**#{idx+1}**"
        lines.append(f"{medal} {name} — Level **{rec.get('level',0)}** · {rec.get('xp',0)} XP")

    embed = base_embed("🏆 XP Leaderboard", "\n".join(lines))
    await i.response.send_message(embed=embed)


# ── /quest commands ────────────────────────────
quest_group = app_commands.Group(name="quest", description="View and manage your daily/weekly quests.")

@quest_group.command(name="list", description="Show your current quest progress (daily & weekly).")
async def slash_quest_list(i: discord.Interaction):
    quest_data = load_quest_data()
    uid        = i.user.id
    gid        = i.guild.id
    all_quests = get_all_quests_for_guild(gid)

    daily_lines  = []
    weekly_lines = []

    for quest in all_quests:
        entry    = get_user_quest_progress(quest_data, gid, uid, quest["id"], quest["reset"])
        progress = min(entry["progress"], quest["target"])
        done     = entry["completed"]
        bar_len  = 10
        filled   = int((progress / quest["target"]) * bar_len)
        bar      = "█" * filled + "░" * (bar_len - filled)
        status   = "✅" if done else "⬜"
        rtype    = quest.get("reward_type", "xp")
        reward_icon = "⭐" if rtype == "xp" else "🎟️" if rtype == "code" else "⭐🎟️"
        line = (
            f"{status} **{quest['name']}**\n"
            f"┗ {quest['desc']} | `[{bar}]` {progress}/{quest['target']}\n"
            f"┗ {reward_icon} {quest['reward']}"
        )
        if quest["reset"] == "daily":
            daily_lines.append(line)
        else:
            weekly_lines.append(line)

    save_quest_data(quest_data)

    embed = base_embed("🎯 Your Quests", "Complete quests to earn rewards!")
    embed.add_field(name="☀️ Daily Quests",  value="\n\n".join(daily_lines)  or "None", inline=False)
    embed.add_field(name="📅 Weekly Quests", value="\n\n".join(weekly_lines) or "None", inline=False)
    embed.set_footer(text="Daily resets midnight WIB • Weekly resets Monday • ⭐=XP 🎟️=Code")
    await i.response.send_message(embed=embed)


@quest_group.command(name="info", description="Show info about the quest system and reward types.")
async def slash_quest_info(i: discord.Interaction):
    embed = base_embed(
        "📋 Quest System Info",
        "Complete Discord activities to earn rewards!\n\n"
        "**Quest Types:**\n"
        "• 💬 **Messages** — Send messages in any channel\n"
        "• 😄 **Reactions** — React to messages\n"
        "• 🤝 **Replies** — Reply to other members\n"
        "• 🌅 **Early Bird** — Send messages before 9 AM WIB\n\n"
        "**Reward Types:**\n"
        "• ⭐ **XP** — Langsung ditambah ke level kamu\n"
        "• 🎟️ **Code** — Kode redeem dikirim lewat DM\n"
        "• ⭐🎟️ **Both** — XP + kode redeem sekaligus\n\n"
        "Gunakan `/quest list` untuk lihat progress."
    )
    await i.response.send_message(embed=embed)


# ── Quest management (admin) ──────────────────────────────────────────────
quest_admin = app_commands.Group(
    name="questadmin",
    description="Manage custom quests and redeem codes. (Requires Manage Server)"
)

@quest_admin.command(name="add", description="Add a custom quest with XP, code, or both as reward.")
@app_commands.describe(
    name="Quest name (e.g. 'VIP Member')",
    desc="Quest description shown to users",
    quest_type="Activity type to track",
    target="How many times to complete the activity",
    reset="When the quest resets",
    reward_type="Type of reward",
    reward_xp="XP to award (used if reward_type is xp or both)",
    reward_label="Reward description shown to users (e.g. 'Nitro 1 Month')"
)
@app_commands.choices(
    quest_type=[
        app_commands.Choice(name="Messages (send messages)", value="messages"),
        app_commands.Choice(name="Reactions (add reactions)", value="reactions"),
        app_commands.Choice(name="Replies (reply to messages)", value="replies"),
        app_commands.Choice(name="Early Bird (before 9 AM WIB)", value="early_msgs"),
    ],
    reset=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
    ],
    reward_type=[
        app_commands.Choice(name="⭐ XP only", value="xp"),
        app_commands.Choice(name="🎟️ Redeem code only", value="code"),
        app_commands.Choice(name="⭐🎟️ XP + Redeem code", value="both"),
    ]
)
async def slash_quest_add(
    i: discord.Interaction,
    name: str,
    desc: str,
    quest_type: str,
    target: int,
    reset: str,
    reward_type: str,
    reward_xp: int = 0,
    reward_label: str = ""
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    if target <= 0:
        return await i.response.send_message(embed=error_embed("Target must be at least 1."), ephemeral=True)
    if reward_type in ("xp", "both") and reward_xp <= 0:
        return await i.response.send_message(embed=error_embed("Set reward_xp > 0 for XP rewards."), ephemeral=True)

    custom = load_custom_quests()
    gid    = str(i.guild.id)
    custom.setdefault(gid, [])

    # Generate unique ID
    import hashlib, time
    quest_id = "cq_" + hashlib.md5(f"{gid}{name}{time.time()}".encode()).hexdigest()[:8]

    reward_display = reward_label or (f"{reward_xp} XP" if reward_type == "xp" else "Redeem code")
    if reward_type == "both":
        reward_display = reward_label or f"{reward_xp} XP + Redeem code"

    new_quest = {
        "id":          quest_id,
        "name":        name,
        "desc":        desc,
        "type":        quest_type,
        "target":      target,
        "reward_xp":   reward_xp,
        "reward":      reward_display,
        "reward_type": reward_type,
        "reset":       reset,
        "custom":      True,
    }
    custom[gid].append(new_quest)
    save_custom_quests(custom)

    rtype_label = {"xp": "⭐ XP", "code": "🎟️ Code", "both": "⭐🎟️ XP + Code"}[reward_type]
    embed = success_embed(
        f"Custom quest **{name}** added!\n\n"
        f"🆔 ID: `{quest_id}`\n"
        f"📋 Type: {quest_type} × {target} ({reset})\n"
        f"🎁 Reward: {rtype_label} — {reward_display}\n\n"
        f"{'📥 Add redeem codes with `/questadmin addcodes ' + quest_id + '`' if reward_type in ('code','both') else ''}"
    )
    await i.response.send_message(embed=embed)


@quest_admin.command(name="list", description="List all custom quests in this server.")
async def slash_quest_admin_list(i: discord.Interaction):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    custom = load_custom_quests()
    gid    = str(i.guild.id)
    quests = custom.get(gid, [])
    if not quests:
        return await i.response.send_message(embed=info_embed("📋 Custom Quests", "No custom quests yet. Use `/questadmin add` to create one."))

    codes = load_redeem_codes()
    lines = []
    for q in quests:
        pool       = codes.get(gid, {}).get(q["id"], [])
        available  = sum(1 for c in pool if not c.get("used"))
        total_pool = len(pool)
        rtype      = {"xp": "⭐", "code": "🎟️", "both": "⭐🎟️"}.get(q.get("reward_type","xp"), "⭐")
        lines.append(
            f"**{q['name']}** — `{q['id']}`\n"
            f"┗ {q['desc']} | {q['type']} × {q['target']} ({q['reset']})\n"
            f"┗ {rtype} {q['reward']} | 🎟️ Codes: {available}/{total_pool} available"
        )

    embed = base_embed("📋 Custom Quests", "\n\n".join(lines))
    await i.response.send_message(embed=embed)


@quest_admin.command(name="remove", description="Remove a custom quest by its ID.")
@app_commands.describe(quest_id="The quest ID (from /questadmin list)")
async def slash_quest_remove(i: discord.Interaction, quest_id: str):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    custom = load_custom_quests()
    gid    = str(i.guild.id)
    before = len(custom.get(gid, []))
    custom[gid] = [q for q in custom.get(gid, []) if q["id"] != quest_id]
    if len(custom[gid]) == before:
        return await i.response.send_message(embed=error_embed(f"Quest `{quest_id}` not found."), ephemeral=True)
    save_custom_quests(custom)
    await i.response.send_message(embed=success_embed(f"Quest `{quest_id}` removed."))


@quest_admin.command(name="addcodes", description="Add redeem codes to a quest's code pool.")
@app_commands.describe(
    quest_id="Quest ID (from /questadmin list)",
    codes="Codes separated by commas (e.g. CODE1,CODE2,CODE3) OR leave empty to auto-generate",
    auto_count="If no codes given, how many to auto-generate (default 10)",
    prefix="Prefix for auto-generated codes (default: JOY)"
)
async def slash_quest_addcodes(
    i: discord.Interaction,
    quest_id: str,
    codes: str = "",
    auto_count: int = 10,
    prefix: str = "JOY"
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)

    # Verify quest exists
    all_quests = get_all_quests_for_guild(i.guild.id)
    quest = next((q for q in all_quests if q["id"] == quest_id), None)
    if not quest:
        return await i.response.send_message(embed=error_embed(f"Quest `{quest_id}` not found."), ephemeral=True)

    code_data = load_redeem_codes()
    gid       = str(i.guild.id)
    code_data.setdefault(gid, {}).setdefault(quest_id, [])
    pool = code_data[gid][quest_id]

    added = []
    if codes.strip():
        # Manual codes
        for raw in codes.split(","):
            c = raw.strip()
            if c:
                # Check not duplicate
                if any(x["code"] == c for x in pool):
                    continue
                pool.append({"code": c, "used": False})
                added.append(c)
    else:
        # Auto-generate
        for _ in range(min(auto_count, 200)):
            c = generate_auto_code(prefix)
            pool.append({"code": c, "used": False})
            added.append(c)

    save_redeem_codes(code_data)

    available = sum(1 for x in pool if not x.get("used"))
    embed = success_embed(
        f"Added **{len(added)}** code(s) to **{quest['name']}**\n"
        f"🎟️ Total available: **{available}**\n\n"
        + (f"**Codes added:**\n```\n{chr(10).join(added[:20])}{'...' if len(added)>20 else ''}\n```" if added else "")
    )
    # Also send codes list as a file if > 20
    await i.response.send_message(embed=embed)


@quest_admin.command(name="viewcodes", description="View all redeem codes for a quest (available & used).")
@app_commands.describe(quest_id="Quest ID (from /questadmin list)")
async def slash_quest_viewcodes(i: discord.Interaction, quest_id: str):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    code_data = load_redeem_codes()
    gid       = str(i.guild.id)
    pool      = code_data.get(gid, {}).get(quest_id, [])
    if not pool:
        return await i.response.send_message(embed=info_embed("🎟️ Code Pool", "No codes in pool. Use `/questadmin addcodes`."))

    available = [c["code"] for c in pool if not c.get("used")]
    used      = [c["code"] for c in pool if c.get("used")]

    text = f"**Quest:** `{quest_id}`\n\n"
    text += f"✅ Available ({len(available)}):\n"
    text += ("```\n" + "\n".join(available[:30]) + ("..." if len(available)>30 else "") + "\n```") if available else "*(none)*\n"
    text += f"\n❌ Used ({len(used)}):\n"
    text += ("```\n" + "\n".join(used[:15]) + ("..." if len(used)>15 else "") + "\n```") if used else "*(none)*"

    await i.response.send_message(embed=base_embed("🎟️ Code Pool", text), ephemeral=True)


@quest_admin.command(name="clearcodes", description="Clear all UNUSED codes from a quest's pool.")
@app_commands.describe(quest_id="Quest ID to clear unused codes from")
async def slash_quest_clearcodes(i: discord.Interaction, quest_id: str):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    code_data = load_redeem_codes()
    gid       = str(i.guild.id)
    pool      = code_data.get(gid, {}).get(quest_id, [])
    before    = sum(1 for c in pool if not c.get("used"))
    # Keep only used ones
    code_data.setdefault(gid, {})[quest_id] = [c for c in pool if c.get("used")]
    save_redeem_codes(code_data)
    await i.response.send_message(embed=success_embed(f"Cleared **{before}** unused code(s) from `{quest_id}`."))


bot.tree.add_command(quest_group)
bot.tree.add_command(quest_admin)


# ── /xp slash command group ────────────────────
xp_group = app_commands.Group(name="xp", description="Manage XP for server members.")

@xp_group.command(name="add", description="Add xp to the member.")
@app_commands.describe(member="The member to add XP to", amount="Amount of XP to add")
async def slash_xp_add(i: discord.Interaction, member: discord.Member, amount: int):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    if amount <= 0:
        return await i.response.send_message(embed=error_embed("Amount must be positive."), ephemeral=True)
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, i.guild.id, member.id)
    old_lv   = user_rec["level"]
    user_rec["xp"] += amount
    new_lv   = level_from_xp(user_rec["xp"])
    user_rec["level"] = new_lv
    save_xp_data(xp_data)

    embed = success_embed(f"Added **{amount} XP** to {member.mention}.\nThey now have **{user_rec['xp']} XP** (Level **{new_lv}**).")
    await i.response.send_message(embed=embed)

    if new_lv > old_lv:
        gc = guild_cfg(cfg, i.guild.id)
        notif_ch_id = gc.get("levelup_channel") or gc.get("main_channel")
        notif_ch = i.guild.get_channel(notif_ch_id) if notif_ch_id else i.channel
        try:
            await notif_ch.send(f"{member.mention} Mencapai Level **{new_lv}**. KELAZZZ👑!")
        except Exception:
            pass


@xp_group.command(name="remove", description="Remove xp from the member.")
@app_commands.describe(member="The member to remove XP from", amount="Amount of XP to remove")
async def slash_xp_remove(i: discord.Interaction, member: discord.Member, amount: int):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    if amount <= 0:
        return await i.response.send_message(embed=error_embed("Amount must be positive."), ephemeral=True)
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, i.guild.id, member.id)
    user_rec["xp"] = max(0, user_rec["xp"] - amount)
    user_rec["level"] = level_from_xp(user_rec["xp"])
    save_xp_data(xp_data)
    await i.response.send_message(embed=success_embed(
        f"Removed **{amount} XP** from {member.mention}.\nThey now have **{user_rec['xp']} XP** (Level **{user_rec['level']}**)."))


@xp_group.command(name="set_level", description="Change the member's level.")
@app_commands.describe(member="The member to set level", level="The level to set")
async def slash_xp_set_level(i: discord.Interaction, member: discord.Member, level: int):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    if level < 0:
        return await i.response.send_message(embed=error_embed("Level must be 0 or higher."), ephemeral=True)
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, i.guild.id, member.id)
    # Calculate total XP for the given level
    total_xp = sum(xp_for_level(lv) for lv in range(level))
    user_rec["xp"]    = total_xp
    user_rec["level"] = level
    save_xp_data(xp_data)
    await i.response.send_message(embed=success_embed(
        f"Set {member.mention}'s level to **{level}** ({total_xp} XP)."))


@xp_group.command(name="set", description="Set the exact XP amount for a member.")
@app_commands.describe(member="The member to set XP for", amount="The XP amount to set")
async def slash_xp_set(i: discord.Interaction, member: discord.Member, amount: int):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    if amount < 0:
        return await i.response.send_message(embed=error_embed("Amount must be 0 or higher."), ephemeral=True)
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, i.guild.id, member.id)
    user_rec["xp"]    = amount
    user_rec["level"] = level_from_xp(amount)
    save_xp_data(xp_data)
    await i.response.send_message(embed=success_embed(
        f"Set {member.mention}'s XP to **{amount}** (Level **{user_rec['level']}**)."))


@xp_group.command(name="setchannel", description="Set the channel where level-up notifications are sent.")
@app_commands.describe(channel="The channel to send level-up notifications to")
async def slash_xp_setchannel(i: discord.Interaction, channel: discord.TextChannel):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed("You need Manage Server permission."), ephemeral=True)
    gc = guild_cfg(cfg, i.guild.id)
    gc["levelup_channel"] = channel.id
    save_config(cfg)
    await i.response.send_message(embed=success_embed(
        f"Level-up notifications will now be sent to {channel.mention}!"))

bot.tree.add_command(xp_group)

# ── Prefix bridges for XP commands ────────────
@bot.command(name="rank")
async def pfx_rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    xp_data  = load_xp_data()
    user_rec = get_user_xp(xp_data, ctx.guild.id, target.id)
    total_xp = user_rec["xp"]
    level    = user_rec["level"]
    xp_now, xp_need = xp_in_current_level(total_xp)
    msgs     = user_rec.get("total_messages", 0)
    gid      = str(ctx.guild.id)
    guild_data = xp_data.get(gid, {})
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    rank = next((idx+1 for idx, (uid, _) in enumerate(sorted_users) if uid == str(target.id)), "?")
    filled = int((xp_now / xp_need) * 20) if xp_need > 0 else 20
    bar = "█" * filled + "░" * (20 - filled)
    embed = base_embed(f"⭐ {target.display_name}'s Rank")
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🏆 Rank",     value=f"#{rank}",               inline=True)
    embed.add_field(name="📊 Level",    value=str(level),                inline=True)
    embed.add_field(name="✉️ Messages", value=str(msgs),                  inline=True)
    embed.add_field(name="⭐ Total XP", value=str(total_xp),             inline=True)
    embed.add_field(name="📈 Progress", value=f"{xp_now}/{xp_need} XP", inline=True)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━", value=f"`[{bar}]`",  inline=False)
    await ctx.send(embed=embed)

@bot.command(name="leaderboard")
async def pfx_leaderboard(ctx):
    xp_data    = load_xp_data()
    gid        = str(ctx.guild.id)
    guild_data = xp_data.get(gid, {})
    if not guild_data:
        return await ctx.send(embed=info_embed("📊 Leaderboard", "No XP data yet!"))
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)[:10]
    lines  = []
    medals = ["🥇","🥈","🥉"]
    for idx, (uid, rec) in enumerate(sorted_users):
        member = ctx.guild.get_member(int(uid))
        name   = member.display_name if member else f"User {uid}"
        medal  = medals[idx] if idx < 3 else f"**#{idx+1}**"
        lines.append(f"{medal} {name} — Level **{rec.get('level',0)}** · {rec.get('xp',0)} XP")
    await ctx.send(embed=base_embed("🏆 XP Leaderboard", "\n".join(lines)))

# ── Hook XP into existing on_message ──────────

@bot.event
async def on_message(message: discord.Message):
    """Main on_message: anti-spam + XP/quests + prefix routing."""
    if message.author.bot:
        return

    # ── Anti cross-channel spam ───────────────────────────────────────────
    if message.guild:
        uid = message.author.id
        now = discord.utils.utcnow().timestamp()

        has_content = (
            message.content.strip()
            or message.attachments
            or message.embeds
        )

        if has_content:
            fp = _spam_fingerprint(message)

            if fp not in spam_tracker[uid]:
                spam_tracker[uid][fp] = {
                    "channels":  set(),
                    "messages":  [],
                    "first_seen": now,
                }

            entry = spam_tracker[uid][fp]

            if now - entry["first_seen"] <= SPAM_WINDOW:
                entry["channels"].add(message.channel.id)
                entry["messages"].append((message.channel.id, message.id))
                spam_cleanup_times[uid] = now

                channel_count = len(entry["channels"])
                if channel_count >= 2:
                    await _try_delete(message.channel, message.id)

                if channel_count >= SPAM_THRESHOLD:
                    delete_tasks = []
                    for ch_id, msg_id in entry["messages"]:
                        ch = message.guild.get_channel(ch_id)
                        if ch:
                            delete_tasks.append(_try_delete(ch, msg_id))
                    await asyncio.gather(*delete_tasks)

                    banned = False
                    try:
                        await message.guild.ban(
                            message.author,
                            reason="[JoyCannot] Cross-channel spam (auto-detected).",
                            delete_message_days=1
                        )
                        banned = True
                    except discord.Forbidden:
                        pass

                    gc     = guild_cfg(cfg, message.guild.id)
                    log_id = gc["ticket"].get("log_channel")
                    if log_id:
                        log_ch = message.guild.get_channel(log_id)
                        if log_ch:
                            content_type = (
                                "🖼️ Image/File" if message.attachments
                                else "🔗 Link/Invite" if any(
                                    x in (message.content or "") for x in
                                    ["http", "discord.gg", "discord.com/invite"])
                                else "💬 Text"
                            )
                            log_embed = discord.Embed(
                                title="🚨 Anti-Spam — User Actioned",
                                color=0xEF4444,
                                timestamp=discord.utils.utcnow()
                            )
                            log_embed.set_author(
                                name=str(message.author),
                                icon_url=message.author.display_avatar.url
                            )
                            log_embed.add_field(
                                name="👤 User",
                                value=f"{message.author.mention}\n`{message.author.id}`",
                                inline=True
                            )
                            log_embed.add_field(
                                name="⚡ Action",
                                value="🔨 **Banned**" if banned else "⚠️ Kicked (no perm)",
                                inline=True
                            )
                            log_embed.add_field(
                                name="📊 Spam Stats",
                                value=(
                                    f"**Channels hit:** {len(entry['channels'])}\n"
                                    f"**Messages deleted:** {len(entry['messages'])}\n"
                                    f"**Content:** {content_type}\n"
                                    f"**Window:** {SPAM_WINDOW}s"
                                ),
                                inline=True
                            )
                            snippet = (message.content or "")[:100]
                            if snippet:
                                log_embed.add_field(
                                    name="📝 Content Preview",
                                    value=f"```{snippet}```",
                                    inline=False
                                )
                            elif message.attachments:
                                log_embed.add_field(
                                    name="📎 Attachment",
                                    value=message.attachments[0].filename,
                                    inline=False
                                )
                            log_embed.set_footer(text="JoyCannot Anti-Spam System")
                            try:
                                await log_ch.send(embed=log_embed)
                            except Exception:
                                pass

                    spam_tracker.pop(uid, None)
                    return
            else:
                spam_tracker[uid][fp] = {
                    "channels":   {message.channel.id},
                    "messages":   [(message.channel.id, message.id)],
                    "first_seen": now,
                }
                spam_cleanup_times[uid] = now

    # ── XP + Quest processing ─────────────────────────────────────────────
    await process_xp_and_quests(message)

    # ── Prefix command routing ────────────────────────────────────────────
    await bot.process_commands(message)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set.")

    async def main():
        await start_vote_webhook()
        await bot.start(token)

    import asyncio as _asyncio
    _asyncio.run(main())
