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
            "premium_commands": [],   # list of command names locked to premium
            "premium_users":    [],   # global list of user IDs with premium access
            "premium_guilds":   [],   # guild IDs with premium nickname activated
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
                "whitelist_role": None,
                "panels": []
            },
            "warnings": {},
            "active_tickets": {}
        }
        save_config(cfg)
    return cfg["guilds"][gid]

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
    print(f"[JoyCannot] Ready — {len(bot.guilds)} guild(s).")

    # ── Restore premium nicknames for all activated guilds ──
    premium_guilds = set(cfg.get("premium_guilds", []))
    if premium_guilds:
        print(f"[JoyCannot] Restoring premium nicknames for {len(premium_guilds)} guild(s)...")
        for guild in bot.guilds:
            if guild.id in premium_guilds:
                await set_guild_premium_nick(guild, activate=True)
                await asyncio.sleep(0.5)


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


@bot.event
async def on_message(message: discord.Message):
    """Single on_message: anti-spam + prefix routing."""
    if message.author.bot:
        return

    # ── Anti cross-channel spam ───────────────────────────────────────────
    if message.guild:
        uid = message.author.id
        now = discord.utils.utcnow().timestamp()

        # Only track if message has any detectable content
        has_content = (
            message.content.strip()
            or message.attachments
            or message.embeds
        )

        if has_content:
            fp = _spam_fingerprint(message)

            # Init tracker entry for this fingerprint if needed
            if fp not in spam_tracker[uid]:
                spam_tracker[uid][fp] = {
                    "channels":  set(),
                    "messages":  [],   # list of (channel_id, message_id) to delete
                    "first_seen": now,
                }

            entry = spam_tracker[uid][fp]

            # Only count within SPAM_WINDOW
            if now - entry["first_seen"] <= SPAM_WINDOW:
                entry["channels"].add(message.channel.id)
                entry["messages"].append((message.channel.id, message.id))
                spam_cleanup_times[uid] = now

                # ── PREEMPTIVE DELETE ─────────────────────────────────────
                # If this fingerprint already appeared in at least 1 other
                # channel, delete the new message immediately — don't wait
                # for the full threshold. Spammers send all at once so by
                # the time we hit threshold the damage is already done.
                channel_count = len(entry["channels"])
                if channel_count >= 2:
                    await _try_delete(message.channel, message.id)

                if channel_count >= SPAM_THRESHOLD:
                    # ── Delete all remaining tracked spam messages ────────
                    delete_tasks = []
                    for ch_id, msg_id in entry["messages"]:
                        ch = message.guild.get_channel(ch_id)
                        if ch:
                            delete_tasks.append(_try_delete(ch, msg_id))
                    await asyncio.gather(*delete_tasks)

                    # ── Ban the spammer ───────────────────────────────────
                    try:
                        await message.guild.ban(
                            message.author,
                            reason="[JoyCannot] Cross-channel spam (auto-detected).",
                            delete_message_days=1
                        )
                    except discord.Forbidden:
                        pass

                    # ── Log to ticket log channel ─────────────────────────
                    gc     = guild_cfg(cfg, message.guild.id)
                    log_id = gc["ticket"].get("log_channel")
                    if log_id:
                        log_ch = message.guild.get_channel(log_id)
                        if log_ch:
                            log_embed = error_embed(
                                t(cfg, message.guild.id, "antispam_ban", user=str(message.author)))
                            log_embed.add_field(
                                name="📋 Detail",
                                value=(
                                    f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                                    f"**Channels spammed:** {len(entry['channels'])}\n"
                                    f"**Messages deleted:** {len(entry['messages'])}\n"
                                    f"**Content type:** "
                                    f"{'Image/File' if message.attachments else 'Link/Text'}"
                                ),
                                inline=False
                            )
                            try:
                                await log_ch.send(embed=log_embed)
                            except Exception:
                                pass

                    spam_tracker.pop(uid, None)
                    return
            else:
                # Window expired for this fingerprint — reset it
                spam_tracker[uid][fp] = {
                    "channels":   {message.channel.id},
                    "messages":   [(message.channel.id, message.id)],
                    "first_seen": now,
                }
                spam_cleanup_times[uid] = now

    # ── Prefix command routing ────────────────────────────────────────────
    await bot.process_commands(message)


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

@bot.tree.command(name="addemoji", description="Add a custom emoji to this server from an image URL. Requires Manage Emojis.")
@app_commands.describe(
    name="Name for the new emoji (letters, numbers, underscores only)",
    url="Direct image URL (.png, .jpg, .gif) — max 256 KB"
)
async def slash_addemoji(i: discord.Interaction, name: str, url: str):
    if not i.user.guild_permissions.manage_emojis:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    await i.response.defer()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        emoji = await i.guild.create_custom_emoji(name=name, image=data)
        await i.followup.send(embed=success_embed(t(cfg, i.guild.id, "emoji_add", name=emoji.name) + f" {emoji}"))
    except Exception as e:
        await i.followup.send(embed=error_embed(f"Failed: {e}"), ephemeral=True)

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

@ticket_group.command(name="setup", description="Configure the ticket system: category, log channel, and optional role restriction.")
@app_commands.describe(
    category="The category where new ticket channels will be created",
    log_channel="Channel where ticket open/close events are logged",
    whitelist_role="Only members with this role can open tickets (leave blank = everyone)"
)
async def slash_ticket_setup(
    i: discord.Interaction,
    category: discord.CategoryChannel,
    log_channel: discord.TextChannel,
    whitelist_role: Optional[discord.Role] = None
):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    gc = guild_cfg(cfg, i.guild.id)
    gc["ticket"]["category"]      = category.id
    gc["ticket"]["log_channel"]   = log_channel.id
    gc["ticket"]["whitelist_role"]= whitelist_role.id if whitelist_role else None
    save_config(cfg)
    await i.response.send_message(embed=success_embed(
        f"Ticket system configured!\n"
        f"**Category:** {category.name}\n"
        f"**Log:** {log_channel.mention}\n"
        f"**Whitelist:** {whitelist_role.mention if whitelist_role else 'Everyone'}"
    ))

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

@ticket_group.command(name="close", description="Close and delete this ticket channel. Only usable inside a ticket.")
async def slash_ticket_close(i: discord.Interaction):
    gc = guild_cfg(cfg, i.guild.id)
    for uid, ch_id in list(gc["active_tickets"].items()):
        if ch_id == i.channel.id:
            if not (i.user.guild_permissions.manage_channels or str(i.user.id) == uid):
                return await i.response.send_message(embed=error_embed("You cannot close this ticket."), ephemeral=True)
            await i.response.send_message(embed=info_embed("🔒 Closing...", "Deleting in 5 seconds."))
            await asyncio.sleep(5)
            del gc["active_tickets"][uid]
            save_config(cfg)
            await i.channel.delete(reason="Ticket closed.")
            return
    await i.response.send_message(embed=error_embed("This channel is not a ticket."), ephemeral=True)

bot.tree.add_command(ticket_group)

async def handle_open_ticket(i: discord.Interaction):
    gc  = guild_cfg(cfg, i.guild.id)
    uid = str(i.user.id)

    wl_id = gc["ticket"].get("whitelist_role")
    if wl_id:
        role = i.guild.get_role(wl_id)
        if role and role not in i.user.roles:
            return await i.response.send_message(
                embed=error_embed(f"You need {role.mention} to open a ticket."), ephemeral=True)

    if uid in gc["active_tickets"]:
        existing = i.guild.get_channel(gc["active_tickets"][uid])
        if existing:
            return await i.response.send_message(
                embed=error_embed(t(cfg, i.guild.id, "ticket_exists")), ephemeral=True)
        del gc["active_tickets"][uid]
        save_config(cfg)

    category = i.guild.get_channel(gc["ticket"].get("category"))
    if not category:
        return await i.response.send_message(embed=error_embed("Ticket category not found."), ephemeral=True)

    safe  = re.sub(r"[^a-z0-9]", "", i.user.name.lower()) or "user"
    ovw   = {
        i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        i.user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
        i.guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    ch = await i.guild.create_text_channel(f"ticket-{safe}", category=category, overwrites=ovw)
    gc["active_tickets"][uid] = ch.id
    save_config(cfg)

    await i.response.send_message(
        embed=success_embed(t(cfg, i.guild.id, "ticket_open", channel=ch.mention)), ephemeral=True)

    class CloseView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger,
                           emoji="🔒", custom_id="joy_ticket_close")
        async def close(self, interaction: discord.Interaction, _btn):
            if not (interaction.user.guild_permissions.manage_channels or interaction.user.id == i.user.id):
                return await interaction.response.send_message(
                    embed=error_embed("You cannot close this ticket."), ephemeral=True)
            await interaction.response.send_message(embed=info_embed("🔒 Closing...", "Deleting in 5 seconds."))
            await asyncio.sleep(5)
            inner = guild_cfg(cfg, interaction.guild.id)
            for k, v in list(inner["active_tickets"].items()):
                if v == interaction.channel.id:
                    del inner["active_tickets"][k]
                    save_config(cfg)
                    break
            await interaction.channel.delete(reason="Ticket closed.")

    welcome = base_embed(f"🎫 Ticket — {i.user.display_name}",
        f"Hello {i.user.mention}! Staff will assist you shortly.\nClick **Close Ticket** when resolved.")
    await ch.send(embed=welcome, view=CloseView())

    log_id = gc["ticket"].get("log_channel")
    if log_id:
        log_ch = i.guild.get_channel(log_id)
        if log_ch:
            await log_ch.send(embed=info_embed("📋 Ticket Opened",
                f"**User:** {i.user.mention}\n**Channel:** {ch.mention}"))

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

    # ── Build payment detail string ──────────────────────────────────────
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
        f"**Total:** {pkg.get('price','N/A')}\n"
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
        "pkg":        pkg,
        "payment":    payment,
        "pay_detail": pay_detail,
        "guild_id":   i.guild.id,
        "guild_name": i.guild.name,
        "user":       i.user,
        "dm_channel": dm_channel,
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
            # Timeout — cancel order
            pending_proofs.pop(i.user.id, None)
            try:
                await dm_channel.send(embed=error_embed(
                    "⏰ Waktu habis! Order kamu dibatalkan karena bukti pembayaran tidak diterima dalam 15 menit.\n"
                    "Silakan `/premium order` lagi jika masih ingin berlangganan."))
            except Exception:
                pass
            return

        pending_proofs.pop(i.user.id, None)

        # ── Build order embed for owner ──────────────────────────────────
        order_embed = base_embed("💎 New Premium Order — Bukti Diterima",
            f"**Package:** {pkg['name']}\n"
            f"**Duration:** {pkg.get('duration','N/A')}\n"
            f"**Price:** {pkg.get('price','N/A')}\n"
            f"**Payment:** {payment.upper()}\n"
            f"**Ordered by:** {i.user.mention} (`{i.user.id}`)\n"
            f"**Server:** {i.guild.name} (`{i.guild.id}`)",
            color=0x22C55E)

        # ── If user sent text along with proof ──────────────────────────
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
                # Forward text embed first
                await owner.send(embed=order_embed, view=btn_view)
                # Forward all attachments (screenshot, etc)
                for att in proof_msg.attachments:
                    await owner.send(
                        content=f"📎 **Bukti pembayaran dari {i.user}:**",
                        file=await att.to_file())
            except Exception:
                pass

        # ── Confirm to buyer ─────────────────────────────────────────────
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
async def pfx_addemoji(ctx, name: str, url: str):
    if not ctx.author.guild_permissions.manage_emojis:
        return await ctx.send(embed=error_embed(t(cfg, ctx.guild.id, "no_perm")))
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        emoji = await ctx.guild.create_custom_emoji(name=name, image=data)
        await ctx.send(embed=success_embed(t(cfg, ctx.guild.id, "emoji_add", name=emoji.name) + f" {emoji}"))
    except Exception as e:
        await ctx.send(embed=error_embed(f"Failed: {e}"))

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
            # Defer so we can do the async nickname change
            await i.response.defer()
            await set_guild_premium_nick(guild, activate=True)
            await i.followup.send(
                embed=success_embed(
                    f"✅ Premium nickname activated for **{guild.name}**!\n"
                    f"Bot nickname is now `{PREMIUM_NICK}` in that server."),
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
            await i.followup.send(
                embed=success_embed(
                    f"✅ Premium nickname deactivated for **{guild.name}**.\n"
                    f"Bot nickname has been reset."),
                ephemeral=True)
            await i.edit_original_response(embed=build_premium_embed(), view=PremiumManagerView(i.user.id))


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

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set.")
    bot.run(token, log_handler=None, reconnect=True)
