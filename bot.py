"""
JoyCannot Discord Bot
Author: JoyCannot Team
Version: 1.1.0
License: MIT

Fixes v1.1.0:
  - Premium setup now uses embed + interactive button UI
  - Slash commands also respond to prefix (except owner-only prefix cmds)
  - Event system: live countdown embed → "Started" edit → "Ended" edit
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
            "payment_methods": {"qris": True, "bank": True, "ewallet": True}
        }
        save_config(default)
        return default
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

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

bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    help_command=None,
    owner_id=int(os.getenv("OWNER_ID", "0")),
)

cfg = load_config()

# Anti-spam tracker
spam_tracker:      dict[int, dict[str, set]] = defaultdict(lambda: defaultdict(set))
spam_cleanup_times: dict[int, float]          = {}
SPAM_THRESHOLD = 3
SPAM_WINDOW    = 8.0

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  FIX #2 — SLASH COMMANDS VIA PREFIX TOO
#  We intercept non-owner prefix messages and
#  route them to the slash command tree.
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

OWNER_ONLY_CMDS = {"maintenance", "premium", "setchannel"}

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[JoyCannot] Ready as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[JoyCannot] Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"[JoyCannot] Sync error: {e}")
    cleanup_spam_cache.start()


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

    # ── Anti cross-channel spam ──────────────────────
    if message.guild and message.content.strip():
        uid     = message.author.id
        content = message.content.strip()
        now     = discord.utils.utcnow().timestamp()
        spam_tracker[uid][content].add(message.channel.id)
        spam_cleanup_times[uid] = now

        if len(spam_tracker[uid][content]) >= SPAM_THRESHOLD:
            try:
                await message.guild.ban(message.author, reason="[JoyCannot] Cross-channel spam.", delete_message_days=1)
                gc     = guild_cfg(cfg, message.guild.id)
                log_id = gc["ticket"].get("log_channel")
                if log_id:
                    ch = message.guild.get_channel(log_id)
                    if ch:
                        await ch.send(embed=error_embed(
                            t(cfg, message.guild.id, "antispam_ban", user=str(message.author))))
            except discord.Forbidden:
                pass
            spam_tracker.pop(uid, None)
            return

    # ── FIX #2: prefix → slash bridge ───────────────
    # If someone uses "!Joy <cmd>" but it's not an owner-only cmd,
    # we simulate a slash command response via ctx.
    await bot.process_commands(message)


# ─────────────────────────────────────────────
# BACKGROUND TASKS
# ─────────────────────────────────────────────

@tasks.loop(seconds=10)
async def cleanup_spam_cache():
    now   = discord.utils.utcnow().timestamp()
    stale = [u for u, ts in spam_cleanup_times.items() if now - ts > SPAM_WINDOW]
    for u in stale:
        spam_tracker.pop(u, None)
        spam_cleanup_times.pop(u, None)

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
    embed = base_embed("📖 JoyCannot — Command List",
        "All commands work as `/slash` **and** `!Joy prefix`.")
    embed.add_field(name="🛡️ Moderation", value=(
        "`kick` `ban` `timeout` `warn`\n"
        "`addrole` `removerole` `move`\n"
        "`userinfo` `avatar` `addemoji` `ping`"
    ), inline=False)
    embed.add_field(name="🎫 Tickets", value=(
        "`ticket setup` · `ticket panel` · `ticket close`"
    ), inline=False)
    embed.add_field(name="📅 Events", value=(
        "`event create` · `event channel`"
    ), inline=False)
    embed.add_field(name="🌐 Language", value=(
        "`language set` · `language list`"
    ), inline=False)
    embed.add_field(name="💎 Premium", value=(
        "`premium info` · `premium order`"
    ), inline=False)
    embed.add_field(name="👑 Owner Only (prefix)", value=(
        "`!Joy maintenance` · `!Joy premium` · `!Joy setchannel`"
    ), inline=False)
    await reply_fn(embed=embed)

# ─────────────────────────────────────────────
# ══════════════════════════════════════════
#  SLASH COMMANDS
# ══════════════════════════════════════════
# ─────────────────────────────────────────────

# ── MODERATION ────────────────────────────────

@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.describe(member="Member to kick", reason="Reason")
async def slash_kick(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_kick(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.describe(member="Member to ban", reason="Reason")
async def slash_ban(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_ban(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="timeout", description="Timeout a member.")
@app_commands.describe(member="Member", minutes="Duration in minutes", reason="Reason")
async def slash_timeout(i: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided."):
    await do_timeout(i.guild, i.user, member, minutes, reason, i.response.send_message)

@bot.tree.command(name="warn", description="Warn a member.")
@app_commands.describe(member="Member", reason="Reason")
async def slash_warn(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    await do_warn(i.guild, i.user, member, reason, i.response.send_message)

@bot.tree.command(name="addrole", description="Add a role to a member.")
@app_commands.describe(member="Target member", role="Role to add")
async def slash_addrole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    await do_addrole(i.guild, i.user, member, role, i.response.send_message)

@bot.tree.command(name="removerole", description="Remove a role from a member.")
@app_commands.describe(member="Target member", role="Role to remove")
async def slash_removerole(i: discord.Interaction, member: discord.Member, role: discord.Role):
    await do_removerole(i.guild, i.user, member, role, i.response.send_message)

@bot.tree.command(name="move", description="Move a member to a voice channel.")
@app_commands.describe(member="Member", channel="Target voice channel")
async def slash_move(i: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    await do_move(i.guild, i.user, member, channel, i.response.send_message)

@bot.tree.command(name="userinfo", description="Display info about a member.")
@app_commands.describe(member="Member to inspect")
async def slash_userinfo(i: discord.Interaction, member: Optional[discord.Member] = None):
    await do_userinfo(i.guild, member or i.user, i.response.send_message)

@bot.tree.command(name="avatar", description="Show a member's avatar.")
@app_commands.describe(member="Member")
async def slash_avatar(i: discord.Interaction, member: Optional[discord.Member] = None):
    await do_avatar(member or i.user, i.response.send_message)

@bot.tree.command(name="ping", description="Check bot latency.")
async def slash_ping(i: discord.Interaction):
    await do_ping(i.response.send_message)

@bot.tree.command(name="help", description="Show all commands.")
async def slash_help(i: discord.Interaction):
    await do_help(i.response.send_message)

@bot.tree.command(name="addemoji", description="Add a custom emoji from URL.")
@app_commands.describe(name="Emoji name", url="Image URL")
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

lang_group = app_commands.Group(name="language", description="Language settings.")

@lang_group.command(name="set", description="Set bot language for this server.")
@app_commands.describe(lang="Language code")
async def slash_lang_set(i: discord.Interaction, lang: str):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    if lang not in LANGUAGES:
        return await i.response.send_message(
            embed=error_embed(f"Valid codes: {', '.join(LANGUAGES.keys())}"), ephemeral=True)
    guild_cfg(cfg, i.guild.id)["language"] = lang
    save_config(cfg)
    await i.response.send_message(embed=success_embed(t(cfg, i.guild.id, "lang_set", lang=LANGUAGES[lang])))

@lang_group.command(name="list", description="List supported languages.")
async def slash_lang_list(i: discord.Interaction):
    cur   = guild_cfg(cfg, i.guild.id).get("language", "en")
    lines = "\n".join(f"{'✅' if k==cur else '◽'} `{k}` — {v}" for k, v in LANGUAGES.items())
    await i.response.send_message(embed=info_embed("🌐 Supported Languages", lines))

bot.tree.add_command(lang_group)

# ── TICKET ────────────────────────────────────

ticket_group = app_commands.Group(name="ticket", description="Ticket system.")

@ticket_group.command(name="setup", description="Configure the ticket system.")
@app_commands.describe(category="Category for tickets", log_channel="Log channel", whitelist_role="Role allowed to open tickets")
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

@ticket_group.command(name="panel", description="Send a ticket panel.")
@app_commands.describe(title="Embed title", description="Embed description", button_label="Button label")
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

@ticket_group.command(name="close", description="Close the current ticket.")
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

premium_slash = app_commands.Group(name="premium", description="Premium packages.")

@premium_slash.command(name="info", description="View premium packages.")
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
    methods = [k.upper() for k, v in pm.items() if v]
    embed.add_field(name="💳 Payment Methods", value=" · ".join(methods) or "None", inline=False)
    await i.response.send_message(embed=embed)

@premium_slash.command(name="order", description="Order a premium package.")
@app_commands.describe(package_name="Package name", payment="Payment method")
@app_commands.choices(payment=[
    app_commands.Choice(name="QRIS",          value="qris"),
    app_commands.Choice(name="Bank Transfer", value="bank"),
    app_commands.Choice(name="E-Wallet",      value="ewallet"),
])
async def slash_premium_order(i: discord.Interaction, package_name: str, payment: str):
    pkg = next((p for p in cfg.get("premium_packages", []) if p["name"].lower() == package_name.lower()), None)
    if not pkg:
        return await i.response.send_message(embed=error_embed("Package not found. Use `/premium info`."), ephemeral=True)
    if not cfg.get("payment_methods", {}).get(payment):
        return await i.response.send_message(embed=error_embed("Payment method not available."), ephemeral=True)

    order_embed = base_embed("💎 New Premium Order",
        f"**Package:** {pkg['name']}\n**Duration:** {pkg.get('duration','N/A')}\n"
        f"**Price:** {pkg.get('price','N/A')}\n**Payment:** {payment.upper()}\n"
        f"**Ordered by:** {i.user.mention} (`{i.user.id}`)\n**Server:** {i.guild.name}")
    owner = await bot.fetch_user(bot.owner_id)
    if owner:
        try:
            v = discord.ui.View()
            v.add_item(discord.ui.Button(label="Contact Buyer",
                url=f"https://discord.com/users/{i.user.id}", style=discord.ButtonStyle.link))
            await owner.send(embed=order_embed, view=v)
        except Exception:
            pass

    confirm = base_embed("✅ Order Received!",
        f"Order for **{pkg['name']}** submitted!\n**Payment:** {payment.upper()}\n"
        f"**Total:** {pkg.get('price','N/A')}\nOur team will DM you shortly.")
    try:
        await i.user.send(embed=confirm)
    except Exception:
        pass
    await i.response.send_message(embed=success_embed("Order submitted! Check your DMs."), ephemeral=True)

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

event_group = app_commands.Group(name="event", description="Event announcement system.")

@event_group.command(name="channel", description="Set the event announcement channel.")
@app_commands.describe(channel="Announce channel")
async def slash_event_channel(i: discord.Interaction, channel: discord.TextChannel):
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(embed=error_embed(t(cfg, i.guild.id, "no_perm")), ephemeral=True)
    guild_cfg(cfg, i.guild.id)["announce_channel"] = channel.id
    save_config(cfg)
    await i.response.send_message(embed=success_embed(f"Announce channel set to {channel.mention}!"))

@event_group.command(name="create", description="Schedule an event with live countdown.")
@app_commands.describe(
    title="Event title",
    name="Event name/topic",
    start_time="Start time WIB (DD/MM/YYYY HH:MM)",
    duration="Duration e.g. 1h, 30m, 1h30m"
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

    embed = base_embed("💎 Premium Package Manager",
        "Manage packages and payment methods below.\n"
        "Use the buttons to add/remove packages or toggle payment methods.")

    if packages:
        pkg_lines = "\n".join(
            f"**{i+1}.** `{p['name']}` — {p['duration']} — {p['type']} — {p['price']}"
            for i, p in enumerate(packages)
        )
    else:
        pkg_lines = "*No packages yet.*"

    embed.add_field(name="📦 Packages", value=pkg_lines, inline=False)
    embed.add_field(name="💳 Payment Methods", value=(
        f"{'✅' if pm.get('qris') else '❌'} QRIS\n"
        f"{'✅' if pm.get('bank') else '❌'} Bank Transfer\n"
        f"{'✅' if pm.get('ewallet') else '❌'} E-Wallet"
    ), inline=False)
    return embed


class PremiumManagerView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    def check_owner(self, i: discord.Interaction) -> bool:
        return i.user.id == self.owner_id

    # ── ADD PACKAGE ───────────────────────────
    @discord.ui.button(label="➕ Add Package", style=discord.ButtonStyle.success, row=0)
    async def add_package(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        await i.response.send_modal(AddPackageModal())

    # ── REMOVE PACKAGE ────────────────────────
    @discord.ui.button(label="🗑️ Remove Package", style=discord.ButtonStyle.danger, row=0)
    async def remove_package(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        packages = cfg.get("premium_packages", [])
        if not packages:
            return await i.response.send_message(embed=error_embed("No packages to remove."), ephemeral=True)
        await i.response.send_modal(RemovePackageModal())

    # ── TOGGLE QRIS ───────────────────────────
    @discord.ui.button(label="QRIS 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_qris(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        cfg["payment_methods"]["qris"] = not cfg["payment_methods"].get("qris", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    # ── TOGGLE BANK ───────────────────────────
    @discord.ui.button(label="Bank 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_bank(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        cfg["payment_methods"]["bank"] = not cfg["payment_methods"].get("bank", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    # ── TOGGLE EWALLET ────────────────────────
    @discord.ui.button(label="E-Wallet 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_ewallet(self, i: discord.Interaction, _btn: discord.ui.Button):
        if not self.check_owner(i):
            return await i.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        cfg["payment_methods"]["ewallet"] = not cfg["payment_methods"].get("ewallet", True)
        save_config(cfg)
        await i.response.edit_message(embed=build_premium_embed(), view=self)

    # ── REFRESH ───────────────────────────────
    @discord.ui.button(label="🔃 Refresh", style=discord.ButtonStyle.primary, row=2)
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


@bot.command(name="premium")
@is_owner()
async def pfx_premium(ctx: commands.Context):
    """!Joy premium — Opens the interactive premium manager (owner only)."""
    await ctx.send(embed=build_premium_embed(), view=PremiumManagerView(ctx.author.id))


# ─────────────────────────────────────────────
# ── MAINTENANCE BROADCAST (OWNER PREFIX)
# ─────────────────────────────────────────────

@bot.command(name="maintenance")
@is_owner()
async def pfx_maintenance(ctx: commands.Context, *, args: str = ""):
    """!Joy maintenance <title> | <description> | <button_label> | <button_url>"""
    parts       = [p.strip() for p in args.split("|")]
    title       = parts[0] if len(parts) > 0 else "🔧 Maintenance Notice"
    description = parts[1] if len(parts) > 1 else "The bot is undergoing scheduled maintenance."
    btn_label   = parts[2] if len(parts) > 2 else "Status Page"
    btn_url     = parts[3] if len(parts) > 3 else "https://status.joycannot.xyz"

    embed = base_embed(f"📢 {title}", description, color=0xF59E0B)
    embed.add_field(name="Sent by", value=str(ctx.author), inline=True)
    embed.add_field(name="Time", value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=True)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=btn_label, url=btn_url, style=discord.ButtonStyle.link))

    ok, fail = 0, 0
    status_msg = await ctx.send(embed=info_embed("📤 Broadcasting...", f"Sending to **{len(bot.guilds)}** servers..."))

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
                await ch.send(embed=embed, view=view)
                ok += 1
            except Exception:
                fail += 1
        else:
            fail += 1
        await asyncio.sleep(0.5)

    await status_msg.edit(embed=success_embed(
        f"Broadcast complete!\n✅ Success: **{ok}** | ❌ Failed: **{fail}**"))


@bot.command(name="setchannel")
@is_owner()
async def pfx_setchannel(ctx: commands.Context, guild_id: int, channel_id: int):
    """!Joy setchannel <guild_id> <channel_id>"""
    guild_cfg(cfg, guild_id)["main_channel"] = channel_id
    save_config(cfg)
    await ctx.send(embed=success_embed(f"Main channel for `{guild_id}` → `{channel_id}`."))


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
