"""
JoyCannot Discord Bot
Author: JoyCannot Team
Version: 1.0.0
License: MIT
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
from collections import defaultdict
from typing import Optional

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

EMBED_COLOR     = 0xD97706   # Dark orange
BOT_PREFIX      = "!Joy "
CONFIG_PATH     = "data/config.json"
WIB             = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────
# CONFIG MANAGER
# ─────────────────────────────────────────────

def load_config() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        default = {
            "guilds": {},
            "premium_packages": [],
            "payment_methods": {
                "qris": True,
                "bank": True,
                "ewallet": True
            }
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
    "en":  "English",
    "id":  "Indonesian",
    "de":  "German",
    "ar":  "Arabic",
    "th":  "Thai",
    "vi":  "Vietnamese",
    "ja":  "Japanese",
    "ko":  "Korean",
}

STRINGS = {
    "en": {
        "no_perm":          "❌ You do not have permission to use this command.",
        "kick_success":     "✅ {user} has been kicked. Reason: {reason}",
        "ban_success":      "✅ {user} has been banned. Reason: {reason}",
        "timeout_success":  "✅ {user} has been timed out for {duration} minutes.",
        "warn_success":     "⚠️ {user} has been warned. Reason: {reason}",
        "role_add":         "✅ Role {role} added to {user}.",
        "role_remove":      "✅ Role {role} removed from {user}.",
        "move_success":     "✅ {user} moved to {channel}.",
        "emoji_add":        "✅ Emoji {name} added.",
        "ticket_open":      "🎫 Your ticket has been created: {channel}",
        "ticket_exists":    "❌ You already have an open ticket.",
        "event_created":    "📅 Event **{name}** scheduled for {time}.",
        "lang_set":         "✅ Language set to {lang}.",
        "no_channel":       "❌ Main channel not configured for this server.",
        "antispam_ban":     "🔨 {user} was banned for cross-channel spam.",
    },
    "id": {
        "no_perm":          "❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.",
        "kick_success":     "✅ {user} telah dikick. Alasan: {reason}",
        "ban_success":      "✅ {user} telah diban. Alasan: {reason}",
        "timeout_success":  "✅ {user} telah di-timeout selama {duration} menit.",
        "warn_success":     "⚠️ {user} telah diperingatkan. Alasan: {reason}",
        "role_add":         "✅ Peran {role} ditambahkan ke {user}.",
        "role_remove":      "✅ Peran {role} dihapus dari {user}.",
        "move_success":     "✅ {user} dipindahkan ke {channel}.",
        "emoji_add":        "✅ Emoji {name} berhasil ditambahkan.",
        "ticket_open":      "🎫 Tiket kamu telah dibuat: {channel}",
        "ticket_exists":    "❌ Kamu sudah memiliki tiket yang terbuka.",
        "event_created":    "📅 Event **{name}** dijadwalkan untuk {time}.",
        "lang_set":         "✅ Bahasa diatur ke {lang}.",
        "no_channel":       "❌ Saluran utama belum dikonfigurasi untuk server ini.",
        "antispam_ban":     "🔨 {user} diban karena spam lintas saluran.",
    },
    "de": {
        "no_perm":          "❌ Du hast keine Berechtigung, diesen Befehl zu verwenden.",
        "kick_success":     "✅ {user} wurde gekickt. Grund: {reason}",
        "ban_success":      "✅ {user} wurde gebannt. Grund: {reason}",
        "timeout_success":  "✅ {user} wurde für {duration} Minuten stummgeschaltet.",
        "warn_success":     "⚠️ {user} wurde verwarnt. Grund: {reason}",
        "role_add":         "✅ Rolle {role} zu {user} hinzugefügt.",
        "role_remove":      "✅ Rolle {role} von {user} entfernt.",
        "move_success":     "✅ {user} wurde nach {channel} verschoben.",
        "emoji_add":        "✅ Emoji {name} hinzugefügt.",
        "ticket_open":      "🎫 Dein Ticket wurde erstellt: {channel}",
        "ticket_exists":    "❌ Du hast bereits ein offenes Ticket.",
        "event_created":    "📅 Event **{name}** geplant für {time}.",
        "lang_set":         "✅ Sprache auf {lang} gesetzt.",
        "no_channel":       "❌ Hauptkanal für diesen Server nicht konfiguriert.",
        "antispam_ban":     "🔨 {user} wurde wegen kanalübergreifendem Spam gebannt.",
    },
    "ar": {
        "no_perm":          "❌ ليس لديك صلاحية استخدام هذا الأمر.",
        "kick_success":     "✅ تم طرد {user}. السبب: {reason}",
        "ban_success":      "✅ تم حظر {user}. السبب: {reason}",
        "timeout_success":  "✅ تم إسكات {user} لمدة {duration} دقيقة.",
        "warn_success":     "⚠️ تم تحذير {user}. السبب: {reason}",
        "role_add":         "✅ تمت إضافة دور {role} إلى {user}.",
        "role_remove":      "✅ تمت إزالة دور {role} من {user}.",
        "move_success":     "✅ تم نقل {user} إلى {channel}.",
        "emoji_add":        "✅ تمت إضافة الإيموجي {name}.",
        "ticket_open":      "🎫 تم إنشاء تذكرتك: {channel}",
        "ticket_exists":    "❌ لديك تذكرة مفتوحة بالفعل.",
        "event_created":    "📅 تم جدولة الحدث **{name}** في {time}.",
        "lang_set":         "✅ تم ضبط اللغة على {lang}.",
        "no_channel":       "❌ لم يتم تكوين القناة الرئيسية لهذا الخادم.",
        "antispam_ban":     "🔨 تم حظر {user} بسبب الرسائل المتكررة عبر القنوات.",
    },
    "th": {
        "no_perm":          "❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
        "kick_success":     "✅ {user} ถูกเตะออกแล้ว เหตุผล: {reason}",
        "ban_success":      "✅ {user} ถูกแบนแล้ว เหตุผล: {reason}",
        "timeout_success":  "✅ {user} ถูก timeout {duration} นาที",
        "warn_success":     "⚠️ {user} ได้รับคำเตือน เหตุผล: {reason}",
        "role_add":         "✅ เพิ่มบทบาท {role} ให้ {user} แล้ว",
        "role_remove":      "✅ นำบทบาท {role} ออกจาก {user} แล้ว",
        "move_success":     "✅ ย้าย {user} ไปที่ {channel} แล้ว",
        "emoji_add":        "✅ เพิ่มอิโมจิ {name} แล้ว",
        "ticket_open":      "🎫 สร้างตั๋วของคุณแล้ว: {channel}",
        "ticket_exists":    "❌ คุณมีตั๋วที่เปิดอยู่แล้ว",
        "event_created":    "📅 กิจกรรม **{name}** นัดหมายที่ {time}",
        "lang_set":         "✅ ตั้งภาษาเป็น {lang} แล้ว",
        "no_channel":       "❌ ยังไม่ได้ตั้งค่าช่องหลักสำหรับเซิร์ฟเวอร์นี้",
        "antispam_ban":     "🔨 {user} ถูกแบนเนื่องจากส่งข้อความซ้ำในหลายช่อง",
    },
    "vi": {
        "no_perm":          "❌ Bạn không có quyền sử dụng lệnh này.",
        "kick_success":     "✅ {user} đã bị kick. Lý do: {reason}",
        "ban_success":      "✅ {user} đã bị ban. Lý do: {reason}",
        "timeout_success":  "✅ {user} đã bị timeout {duration} phút.",
        "warn_success":     "⚠️ {user} đã bị cảnh báo. Lý do: {reason}",
        "role_add":         "✅ Đã thêm vai trò {role} cho {user}.",
        "role_remove":      "✅ Đã xóa vai trò {role} khỏi {user}.",
        "move_success":     "✅ Đã chuyển {user} sang {channel}.",
        "emoji_add":        "✅ Đã thêm emoji {name}.",
        "ticket_open":      "🎫 Ticket của bạn đã được tạo: {channel}",
        "ticket_exists":    "❌ Bạn đã có ticket đang mở.",
        "event_created":    "📅 Sự kiện **{name}** đã được lên lịch lúc {time}.",
        "lang_set":         "✅ Ngôn ngữ đã được đặt thành {lang}.",
        "no_channel":       "❌ Kênh chính chưa được cấu hình cho máy chủ này.",
        "antispam_ban":     "🔨 {user} đã bị ban do spam trên nhiều kênh.",
    },
    "ja": {
        "no_perm":          "❌ このコマンドを使用する権限がありません。",
        "kick_success":     "✅ {user} をキックしました。理由: {reason}",
        "ban_success":      "✅ {user} をBANしました。理由: {reason}",
        "timeout_success":  "✅ {user} を{duration}分タイムアウトしました。",
        "warn_success":     "⚠️ {user} に警告を送りました。理由: {reason}",
        "role_add":         "✅ {user} にロール {role} を付与しました。",
        "role_remove":      "✅ {user} からロール {role} を削除しました。",
        "move_success":     "✅ {user} を {channel} に移動しました。",
        "emoji_add":        "✅ 絵文字 {name} を追加しました。",
        "ticket_open":      "🎫 チケットが作成されました: {channel}",
        "ticket_exists":    "❌ すでに開いているチケットがあります。",
        "event_created":    "📅 イベント **{name}** を {time} に設定しました。",
        "lang_set":         "✅ 言語を {lang} に設定しました。",
        "no_channel":       "❌ このサーバーのメインチャンネルが設定されていません。",
        "antispam_ban":     "🔨 {user} は複数チャンネルへのスパムのためBANされました。",
    },
    "ko": {
        "no_perm":          "❌ 이 명령어를 사용할 권한이 없습니다.",
        "kick_success":     "✅ {user}을(를) 추방했습니다. 사유: {reason}",
        "ban_success":      "✅ {user}을(를) 차단했습니다. 사유: {reason}",
        "timeout_success":  "✅ {user}을(를) {duration}분 타임아웃했습니다.",
        "warn_success":     "⚠️ {user}에게 경고를 보냈습니다. 사유: {reason}",
        "role_add":         "✅ {user}에게 역할 {role}을(를) 부여했습니다.",
        "role_remove":      "✅ {user}에게서 역할 {role}을(를) 제거했습니다.",
        "move_success":     "✅ {user}을(를) {channel}로 이동했습니다.",
        "emoji_add":        "✅ 이모지 {name}을(를) 추가했습니다.",
        "ticket_open":      "🎫 티켓이 생성되었습니다: {channel}",
        "ticket_exists":    "❌ 이미 열려 있는 티켓이 있습니다.",
        "event_created":    "📅 이벤트 **{name}**이(가) {time}에 예약되었습니다.",
        "lang_set":         "✅ 언어가 {lang}으로 설정되었습니다.",
        "no_channel":       "❌ 이 서버의 메인 채널이 설정되지 않았습니다.",
        "antispam_ban":     "🔨 {user}이(가) 여러 채널에 스팸을 보내 차단되었습니다.",
    },
}


def t(cfg: dict, guild_id: int, key: str, **kwargs) -> str:
    """Translate a string key for the given guild's language."""
    gc   = guild_cfg(cfg, guild_id)
    lang = gc.get("language", "en")
    s    = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
    return s.format(**kwargs)


# ─────────────────────────────────────────────
# EMBED HELPERS
# ─────────────────────────────────────────────

def base_embed(title: str, description: str = "", color: int = EMBED_COLOR) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="JoyCannot Bot", icon_url="https://i.imgur.com/4M34hi2.png")
    embed.timestamp = discord.utils.utcnow()
    return embed


def success_embed(description: str) -> discord.Embed:
    return base_embed("✅ Success", description, 0x22C55E)


def error_embed(description: str) -> discord.Embed:
    return base_embed("❌ Error", description, 0xEF4444)


def info_embed(title: str, description: str) -> discord.Embed:
    return base_embed(title, description)


# ─────────────────────────────────────────────
# DURATION PARSER
# ─────────────────────────────────────────────

def parse_duration(s: str) -> Optional[int]:
    """Parse strings like '30m', '2h', '1h30m' → seconds."""
    pattern = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?")
    m = pattern.fullmatch(s.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    return (h * 3600) + (mins * 60)


# ─────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────

intents = discord.Intents.default()
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

# Anti-spam tracker: user_id → {message_content: set(channel_ids)}
spam_tracker: dict[int, dict[str, set]] = defaultdict(lambda: defaultdict(set))
spam_cleanup_times: dict[int, float]    = {}

SPAM_THRESHOLD = 3   # number of different channels with same message = spam
SPAM_WINDOW    = 8.0  # seconds


# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[JoyCannot] Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[JoyCannot] Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"[JoyCannot] Sync error: {e}")
    cleanup_spam_cache.start()


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Send welcome embed when bot joins a new server."""
    gc = guild_cfg(cfg, guild.id)

    # Find best channel to send welcome message
    target = guild.system_channel
    if not target:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                if "general" in ch.name.lower() or "chat" in ch.name.lower():
                    target = ch
                    break
    if not target:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                target = ch
                break

    if not target:
        return

    embed = base_embed(
        "👋 Thanks for inviting JoyCannot!",
        (
            "Hello! I'm **JoyCannot**, a professional multi-purpose Discord bot.\n\n"
            "**Features:**\n"
            "🛡️ Full Moderation Suite\n"
            "🎫 Advanced Ticket System\n"
            "📅 Event Announcements\n"
            "📢 Maintenance Broadcasts\n"
            "🌐 Multi-language Support (8 languages)\n"
            "💎 Premium Package System\n"
            "🚫 Anti Cross-Channel Spam\n\n"
            "Use `/help` to get started!\n\n"
            "**Setup:** Please select the main channel below for maintenance notifications."
        )
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    class ChannelSelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)

        @discord.ui.select(
            cls=discord.ui.ChannelSelect,
            channel_types=[discord.ChannelType.text],
            placeholder="📌 Select main channel for notifications",
            min_values=1,
            max_values=1,
        )
        async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    embed=error_embed("Only server administrators can set the main channel."),
                    ephemeral=True
                )
                return
            ch = select.values[0]
            gc["main_channel"] = ch.id
            save_config(cfg)
            await interaction.response.send_message(
                embed=success_embed(f"Main channel set to {ch.mention}!"),
                ephemeral=True
            )
            self.stop()

    await target.send(embed=embed, view=ChannelSelectView())


@bot.event
async def on_message(message: discord.Message):
    """Single on_message handler: prefix commands + anti-spam."""
    if message.author.bot:
        return

    # ── Anti cross-channel spam ──────────────────────────
    if message.guild and message.content.strip():
        uid     = message.author.id
        content = message.content.strip()
        now     = discord.utils.utcnow().timestamp()

        spam_tracker[uid][content].add(message.channel.id)
        spam_cleanup_times[uid] = now

        if len(spam_tracker[uid][content]) >= SPAM_THRESHOLD:
            # Cross-channel spam detected
            try:
                await message.guild.ban(
                    message.author,
                    reason="[JoyCannot] Cross-channel spam detected.",
                    delete_message_days=1
                )
                gc = guild_cfg(cfg, message.guild.id)
                lang_msg = t(cfg, message.guild.id, "antispam_ban", user=str(message.author))
                log_ch_id = gc["ticket"].get("log_channel")
                if log_ch_id:
                    log_ch = message.guild.get_channel(log_ch_id)
                    if log_ch:
                        await log_ch.send(embed=error_embed(lang_msg))
            except discord.Forbidden:
                pass
            except Exception:
                pass
            spam_tracker.pop(uid, None)
            return

    await bot.process_commands(message)


# ─────────────────────────────────────────────
# BACKGROUND TASKS
# ─────────────────────────────────────────────

@tasks.loop(seconds=10)
async def cleanup_spam_cache():
    """Remove stale spam tracker entries every 10 seconds."""
    now = discord.utils.utcnow().timestamp()
    stale = [uid for uid, ts in spam_cleanup_times.items() if now - ts > SPAM_WINDOW]
    for uid in stale:
        spam_tracker.pop(uid, None)
        spam_cleanup_times.pop(uid, None)


# ─────────────────────────────────────────────
# ═══════════════════════════════════════════
#  SLASH COMMANDS
# ═══════════════════════════════════════════
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# ──  MODERATION COMMANDS
# ─────────────────────────────────────────────

@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
@app_commands.checks.has_permissions(kick_members=True)
async def cmd_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    try:
        await member.kick(reason=reason)
        msg = t(cfg, interaction.guild.id, "kick_success", user=member.mention, reason=reason)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to kick this user."), ephemeral=True)


@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
@app_commands.checks.has_permissions(ban_members=True)
async def cmd_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    try:
        await member.ban(reason=reason, delete_message_days=1)
        msg = t(cfg, interaction.guild.id, "ban_success", user=member.mention, reason=reason)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to ban this user."), ephemeral=True)


@bot.tree.command(name="timeout", description="Timeout a member.")
@app_commands.describe(member="Member to timeout", minutes="Duration in minutes", reason="Reason")
@app_commands.checks.has_permissions(moderate_members=True)
async def cmd_timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided."):
    try:
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        msg = t(cfg, interaction.guild.id, "timeout_success", user=member.mention, duration=minutes)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to timeout this user."), ephemeral=True)


@bot.tree.command(name="warn", description="Warn a member.")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
@app_commands.checks.has_permissions(manage_messages=True)
async def cmd_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
    gc   = guild_cfg(cfg, interaction.guild.id)
    uid  = str(member.id)
    if uid not in gc["warnings"]:
        gc["warnings"][uid] = []
    gc["warnings"][uid].append({
        "reason": reason,
        "timestamp": discord.utils.utcnow().isoformat(),
        "warned_by": interaction.user.id
    })
    save_config(cfg)
    msg = t(cfg, interaction.guild.id, "warn_success", user=member.mention, reason=reason)
    await interaction.response.send_message(embed=success_embed(msg))
    try:
        dm_embed = base_embed("⚠️ You have been warned", f"**Server:** {interaction.guild.name}\n**Reason:** {reason}")
        await member.send(embed=dm_embed)
    except Exception:
        pass


@bot.tree.command(name="addrole", description="Add a role to a member.")
@app_commands.describe(member="Target member", role="Role to add")
@app_commands.checks.has_permissions(manage_roles=True)
async def cmd_addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await member.add_roles(role)
        msg = t(cfg, interaction.guild.id, "role_add", role=role.mention, user=member.mention)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to manage roles."), ephemeral=True)


@bot.tree.command(name="removerole", description="Remove a role from a member.")
@app_commands.describe(member="Target member", role="Role to remove")
@app_commands.checks.has_permissions(manage_roles=True)
async def cmd_removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await member.remove_roles(role)
        msg = t(cfg, interaction.guild.id, "role_remove", role=role.mention, user=member.mention)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to manage roles."), ephemeral=True)


@bot.tree.command(name="move", description="Move a member to a different voice channel.")
@app_commands.describe(member="Member to move", channel="Target voice channel")
@app_commands.checks.has_permissions(move_members=True)
async def cmd_move(interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    try:
        await member.move_to(channel)
        msg = t(cfg, interaction.guild.id, "move_success", user=member.mention, channel=channel.mention)
        await interaction.response.send_message(embed=success_embed(msg))
    except discord.Forbidden:
        await interaction.response.send_message(embed=error_embed("I lack permission to move members."), ephemeral=True)
    except discord.HTTPException:
        await interaction.response.send_message(embed=error_embed("Member is not in a voice channel."), ephemeral=True)


@bot.tree.command(name="userinfo", description="Display info about a member.")
@app_commands.describe(member="Member to inspect")
async def cmd_userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    member = member or interaction.user
    gc     = guild_cfg(cfg, interaction.guild.id)
    warns  = len(gc["warnings"].get(str(member.id), []))

    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed = base_embed(f"👤 User Info — {member.display_name}")
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Username",    value=str(member),                             inline=True)
    embed.add_field(name="ID",          value=str(member.id),                          inline=True)
    embed.add_field(name="Joined",      value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
    embed.add_field(name="Registered",  value=discord.utils.format_dt(member.created_at, "R"), inline=True)
    embed.add_field(name="Warnings",    value=str(warns),                              inline=True)
    embed.add_field(name="Top Role",    value=member.top_role.mention,                 inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) or "None",     inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Show a member's avatar.")
@app_commands.describe(member="Member whose avatar to display")
async def cmd_avatar(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    member = member or interaction.user
    embed  = base_embed(f"🖼️ Avatar — {member.display_name}")
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="addemoji", description="Add a custom emoji to the server.")
@app_commands.describe(name="Emoji name", url="Image URL for the emoji")
@app_commands.checks.has_permissions(manage_emojis=True)
async def cmd_addemoji(interaction: discord.Interaction, name: str, url: str):
    await interaction.response.defer()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                image_bytes = await resp.read()
        emoji = await interaction.guild.create_custom_emoji(name=name, image=image_bytes)
        msg   = t(cfg, interaction.guild.id, "emoji_add", name=emoji.name)
        await interaction.followup.send(embed=success_embed(msg + f" {emoji}"))
    except Exception as e:
        await interaction.followup.send(embed=error_embed(f"Failed to add emoji: {e}"), ephemeral=True)


@bot.tree.command(name="ping", description="Check the bot's latency.")
async def cmd_ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    embed = info_embed("🏓 Pong!", f"Websocket latency: **{latency_ms}ms**")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show all available commands.")
async def cmd_help(interaction: discord.Interaction):
    embed = base_embed(
        "📖 JoyCannot — Command List",
        "Here's everything you can do with JoyCannot!"
    )
    embed.add_field(name="🛡️ Moderation", value=(
        "`/kick` `/ban` `/timeout` `/warn`\n"
        "`/addrole` `/removerole` `/move`\n"
        "`/userinfo` `/avatar` `/addemoji` `/ping`"
    ), inline=False)
    embed.add_field(name="🎫 Tickets", value=(
        "`/ticket setup` — Configure ticket system\n"
        "`/ticket panel` — Send a ticket panel\n"
        "`/ticket close` — Close current ticket"
    ), inline=False)
    embed.add_field(name="📅 Events", value=(
        "`/event create` — Schedule an event\n"
        "`/event channel` — Set announce channel"
    ), inline=False)
    embed.add_field(name="🌐 Language", value=(
        "`/language set` — Change bot language\n"
        "`/language list` — View supported languages"
    ), inline=False)
    embed.add_field(name="💎 Premium", value=(
        "`/premium info` — View premium packages\n"
        "`/premium order` — Order a premium package"
    ), inline=False)
    embed.add_field(name="👑 Owner Only (prefix)", value=(
        "`!Joy maintenance` — Broadcast to all servers\n"
        "`!Joy premium` — Manage premium packages"
    ), inline=False)
    await interaction.response.send_message(embed=embed)


# ─────────────────────────────────────────────
# ── LANGUAGE COMMANDS
# ─────────────────────────────────────────────

language_group = app_commands.Group(name="language", description="Language settings.")

@language_group.command(name="set", description="Set the bot language for this server.")
@app_commands.describe(lang="Language code (en, id, de, ar, th, vi, ja, ko)")
@app_commands.checks.has_permissions(manage_guild=True)
async def language_set(interaction: discord.Interaction, lang: str):
    if lang not in LANGUAGES:
        await interaction.response.send_message(
            embed=error_embed(f"Unknown language. Use: {', '.join(LANGUAGES.keys())}"),
            ephemeral=True
        )
        return
    gc = guild_cfg(cfg, interaction.guild.id)
    gc["language"] = lang
    save_config(cfg)
    msg = t(cfg, interaction.guild.id, "lang_set", lang=LANGUAGES[lang])
    await interaction.response.send_message(embed=success_embed(msg))

@language_group.command(name="list", description="List all supported languages.")
async def language_list(interaction: discord.Interaction):
    current = guild_cfg(cfg, interaction.guild.id).get("language", "en")
    lines   = "\n".join(f"{'✅' if k == current else '◽'} `{k}` — {v}" for k, v in LANGUAGES.items())
    await interaction.response.send_message(embed=info_embed("🌐 Supported Languages", lines))

bot.tree.add_command(language_group)


# ─────────────────────────────────────────────
# ── TICKET SYSTEM
# ─────────────────────────────────────────────

ticket_group = app_commands.Group(name="ticket", description="Ticket system management.")


@ticket_group.command(name="setup", description="Configure the ticket system.")
@app_commands.describe(
    category="Category for ticket channels",
    log_channel="Channel to log ticket actions",
    whitelist_role="Role allowed to open tickets (leave empty for everyone)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_setup(
    interaction: discord.Interaction,
    category: discord.CategoryChannel,
    log_channel: discord.TextChannel,
    whitelist_role: Optional[discord.Role] = None
):
    gc = guild_cfg(cfg, interaction.guild.id)
    gc["ticket"]["category"]     = category.id
    gc["ticket"]["log_channel"]  = log_channel.id
    gc["ticket"]["whitelist_role"] = whitelist_role.id if whitelist_role else None
    save_config(cfg)
    await interaction.response.send_message(
        embed=success_embed(
            f"Ticket system configured!\n"
            f"**Category:** {category.name}\n"
            f"**Log Channel:** {log_channel.mention}\n"
            f"**Whitelist Role:** {whitelist_role.mention if whitelist_role else 'Everyone'}"
        )
    )


@ticket_group.command(name="panel", description="Send a ticket panel embed with a button.")
@app_commands.describe(
    title="Panel embed title",
    description="Panel embed description",
    button_label="Label for the open-ticket button"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(
    interaction: discord.Interaction,
    title: str = "🎫 Support Tickets",
    description: str = "Click the button below to open a support ticket.",
    button_label: str = "Open Ticket"
):
    gc = guild_cfg(cfg, interaction.guild.id)
    if not gc["ticket"].get("category"):
        await interaction.response.send_message(
            embed=error_embed("Please run `/ticket setup` first."), ephemeral=True
        )
        return

    embed = base_embed(title, description)

    class TicketView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label=button_label, style=discord.ButtonStyle.primary, emoji="🎫", custom_id="joy_ticket_open")
        async def open_ticket(self, i: discord.Interaction, button: discord.ui.Button):
            await handle_open_ticket(i)

    await interaction.response.send_message(embed=embed, view=TicketView())

    # Store panel info
    gc["ticket"]["panels"].append({
        "channel_id": interaction.channel.id,
        "title": title,
        "description": description,
        "button_label": button_label
    })
    save_config(cfg)


async def handle_open_ticket(interaction: discord.Interaction):
    gc  = guild_cfg(cfg, interaction.guild.id)
    uid = str(interaction.user.id)

    # Check whitelist
    wl_role_id = gc["ticket"].get("whitelist_role")
    if wl_role_id:
        wl_role = interaction.guild.get_role(wl_role_id)
        if wl_role and wl_role not in interaction.user.roles:
            await interaction.response.send_message(
                embed=error_embed(f"You need the {wl_role.mention} role to open a ticket."),
                ephemeral=True
            )
            return

    # Check existing ticket
    if uid in gc["active_tickets"]:
        existing = interaction.guild.get_channel(gc["active_tickets"][uid])
        if existing:
            msg = t(cfg, interaction.guild.id, "ticket_exists")
            await interaction.response.send_message(embed=error_embed(msg), ephemeral=True)
            return
        else:
            del gc["active_tickets"][uid]
            save_config(cfg)

    # Create channel
    cat_id   = gc["ticket"].get("category")
    category = interaction.guild.get_channel(cat_id)
    if not category:
        await interaction.response.send_message(embed=error_embed("Ticket category not found."), ephemeral=True)
        return

    safe_name = re.sub(r"[^a-z0-9]", "", interaction.user.name.lower()) or "user"
    ch_name   = f"ticket-{safe_name}"
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
        interaction.guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    channel = await interaction.guild.create_text_channel(ch_name, category=category, overwrites=overwrites)
    gc["active_tickets"][uid] = channel.id
    save_config(cfg)

    msg = t(cfg, interaction.guild.id, "ticket_open", channel=channel.mention)
    await interaction.response.send_message(embed=success_embed(msg), ephemeral=True)

    # Welcome embed in ticket channel
    ticket_embed = base_embed(
        f"🎫 Ticket — {interaction.user.display_name}",
        f"Hello {interaction.user.mention}, welcome to your support ticket!\n"
        "A staff member will assist you shortly.\n\n"
        "Click **Close Ticket** when resolved."
    )

    class CloseView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="joy_ticket_close")
        async def close_ticket(self, i: discord.Interaction, button: discord.ui.Button):
            if not (i.user.guild_permissions.manage_channels or i.user.id == interaction.user.id):
                await i.response.send_message(embed=error_embed("You cannot close this ticket."), ephemeral=True)
                return
            await i.response.send_message(embed=info_embed("🔒 Closing ticket...", "This channel will be deleted in 5 seconds."))
            await asyncio.sleep(5)
            inner_gc = guild_cfg(cfg, i.guild.id)
            for k, v in list(inner_gc["active_tickets"].items()):
                if v == i.channel.id:
                    del inner_gc["active_tickets"][k]
                    save_config(cfg)
                    break
            await i.channel.delete(reason="Ticket closed.")

    await channel.send(embed=ticket_embed, view=CloseView())

    # Log
    log_id = gc["ticket"].get("log_channel")
    if log_id:
        log_ch = interaction.guild.get_channel(log_id)
        if log_ch:
            await log_ch.send(embed=info_embed(
                "📋 Ticket Opened",
                f"**User:** {interaction.user.mention}\n**Channel:** {channel.mention}"
            ))


@ticket_group.command(name="close", description="Close the current ticket channel.")
async def ticket_close(interaction: discord.Interaction):
    gc = guild_cfg(cfg, interaction.guild.id)
    for uid, ch_id in list(gc["active_tickets"].items()):
        if ch_id == interaction.channel.id:
            if not (interaction.user.guild_permissions.manage_channels or str(interaction.user.id) == uid):
                await interaction.response.send_message(embed=error_embed("You cannot close this ticket."), ephemeral=True)
                return
            await interaction.response.send_message(embed=info_embed("🔒 Closing...", "Deleting in 5 seconds."))
            await asyncio.sleep(5)
            del gc["active_tickets"][uid]
            save_config(cfg)
            await interaction.channel.delete(reason="Ticket closed via command.")
            return
    await interaction.response.send_message(embed=error_embed("This channel is not a ticket."), ephemeral=True)


bot.tree.add_command(ticket_group)


# ─────────────────────────────────────────────
# ── EVENT ANNOUNCEMENT SYSTEM
# ─────────────────────────────────────────────

event_group = app_commands.Group(name="event", description="Event announcement system.")


@event_group.command(name="create", description="Create and announce a scheduled event.")
@app_commands.describe(
    title="Event title",
    name="Event name/topic",
    start_time="Start time in WIB (format: DD/MM/YYYY HH:MM)",
    duration="Duration (e.g. 1h, 30m, 1h30m)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def event_create(
    interaction: discord.Interaction,
    title: str,
    name: str,
    start_time: str,
    duration: str
):
    gc = guild_cfg(cfg, interaction.guild.id)
    announce_ch_id = gc.get("announce_channel")
    if not announce_ch_id:
        await interaction.response.send_message(
            embed=error_embed("Announce channel not set. Use `/event channel` first."), ephemeral=True
        )
        return

    announce_ch = interaction.guild.get_channel(announce_ch_id)
    if not announce_ch:
        await interaction.response.send_message(embed=error_embed("Announce channel not found."), ephemeral=True)
        return

    # Parse start time in WIB
    try:
        dt_naive = datetime.datetime.strptime(start_time.strip(), "%d/%m/%Y %H:%M")
        dt_wib   = WIB.localize(dt_naive)
    except ValueError:
        await interaction.response.send_message(
            embed=error_embed("Invalid time format. Use: `DD/MM/YYYY HH:MM` (e.g. `25/12/2025 20:00`)"),
            ephemeral=True
        )
        return

    dur_secs = parse_duration(duration)
    if dur_secs is None:
        await interaction.response.send_message(
            embed=error_embed("Invalid duration format. Use: `1h`, `30m`, `1h30m`"), ephemeral=True
        )
        return

    end_dt       = dt_wib + datetime.timedelta(seconds=dur_secs)
    dur_readable = f"{dur_secs // 3600}h {(dur_secs % 3600) // 60}m".strip()

    embed = base_embed(f"📅 {title}", f"**{name}**\n\nA new event has been scheduled!")
    embed.add_field(name="⏰ Start (WIB)",  value=dt_wib.strftime("%d %B %Y — %H:%M WIB"),  inline=True)
    embed.add_field(name="⏳ Duration",     value=dur_readable,                              inline=True)
    embed.add_field(name="🏁 End (WIB)",   value=end_dt.strftime("%d %B %Y — %H:%M WIB"),   inline=True)
    embed.add_field(name="📌 Countdown",    value=discord.utils.format_dt(dt_wib, "R"),      inline=False)

    await announce_ch.send("@everyone", embed=embed)
    await interaction.response.send_message(
        embed=success_embed(f"Event announced in {announce_ch.mention}!"),
        ephemeral=True
    )

    # Schedule auto countdown reminder 5 mins before
    now_utc  = discord.utils.utcnow()
    start_utc = dt_wib.astimezone(pytz.utc).replace(tzinfo=None)
    delta     = (start_utc - now_utc.replace(tzinfo=None)).total_seconds()
    remind_at = delta - 300  # 5 min before

    if remind_at > 0:
        async def send_reminder():
            await asyncio.sleep(remind_at)
            remind_embed = base_embed(
                f"⏰ Event Starting Soon — {title}",
                f"**{name}** starts in **5 minutes!**"
            )
            await announce_ch.send("@everyone", embed=remind_embed)

        asyncio.create_task(send_reminder())


@event_group.command(name="channel", description="Set the event announcement channel.")
@app_commands.describe(channel="Channel to send event announcements")
@app_commands.checks.has_permissions(manage_guild=True)
async def event_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    gc = guild_cfg(cfg, interaction.guild.id)
    gc["announce_channel"] = channel.id
    save_config(cfg)
    await interaction.response.send_message(embed=success_embed(f"Announce channel set to {channel.mention}!"))


bot.tree.add_command(event_group)


# ─────────────────────────────────────────────
# ── PREMIUM SYSTEM
# ─────────────────────────────────────────────

premium_slash = app_commands.Group(name="premium", description="Premium package system.")


@premium_slash.command(name="info", description="View available premium packages.")
async def premium_info(interaction: discord.Interaction):
    packages = cfg.get("premium_packages", [])
    if not packages:
        await interaction.response.send_message(
            embed=info_embed("💎 Premium Packages", "No premium packages available yet."), ephemeral=True
        )
        return

    embed = base_embed("💎 JoyCannot Premium", "Upgrade your server with premium features!")
    for pkg in packages:
        embed.add_field(
            name=f"{'⭐' if pkg.get('type') == 'basic' else '💎'} {pkg['name']}",
            value=(
                f"**Duration:** {pkg.get('duration', 'N/A')}\n"
                f"**Type:** {pkg.get('type', 'N/A').capitalize()}\n"
                f"**Price:** {pkg.get('price', 'N/A')}"
            ),
            inline=True
        )

    pm = cfg.get("payment_methods", {})
    methods = []
    if pm.get("qris"):    methods.append("QRIS")
    if pm.get("bank"):    methods.append("Bank Transfer")
    if pm.get("ewallet"): methods.append("E-Wallet")
    embed.add_field(name="💳 Payment Methods", value=" • ".join(methods) or "None", inline=False)
    await interaction.response.send_message(embed=embed)


@premium_slash.command(name="order", description="Order a premium package.")
@app_commands.describe(package_name="Name of the package to order", payment="Payment method")
@app_commands.choices(payment=[
    app_commands.Choice(name="QRIS",          value="qris"),
    app_commands.Choice(name="Bank Transfer", value="bank"),
    app_commands.Choice(name="E-Wallet",      value="ewallet"),
])
async def premium_order(interaction: discord.Interaction, package_name: str, payment: str):
    packages = cfg.get("premium_packages", [])
    pkg      = next((p for p in packages if p["name"].lower() == package_name.lower()), None)
    if not pkg:
        await interaction.response.send_message(embed=error_embed("Package not found. Use `/premium info` to view available packages."), ephemeral=True)
        return

    pm = cfg.get("payment_methods", {})
    if not pm.get(payment):
        await interaction.response.send_message(embed=error_embed("This payment method is not available."), ephemeral=True)
        return

    order_embed = base_embed(
        "💎 New Premium Order",
        f"**Package:** {pkg['name']}\n"
        f"**Duration:** {pkg.get('duration', 'N/A')}\n"
        f"**Price:** {pkg.get('price', 'N/A')}\n"
        f"**Payment:** {payment.upper()}\n"
        f"**Ordered by:** {interaction.user.mention} (`{interaction.user.id}`)\n"
        f"**Server:** {interaction.guild.name} (`{interaction.guild.id}`)"
    )

    # DM the owner
    owner = await bot.fetch_user(bot.owner_id)
    if owner:
        try:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Contact Buyer", url=f"https://discord.com/users/{interaction.user.id}", style=discord.ButtonStyle.link))
            await owner.send(embed=order_embed, view=view)
        except Exception:
            pass

    # Confirm to user
    confirm_embed = base_embed(
        "✅ Order Received!",
        f"Your order for **{pkg['name']}** has been submitted.\n\n"
        f"**Payment:** {payment.upper()}\n"
        f"**Total:** {pkg.get('price', 'N/A')}\n\n"
        "Our team will contact you shortly via DM."
    )
    if payment == "qris" and os.path.exists("qris.png"):
        confirm_embed.set_image(url="attachment://qris.png")
        try:
            await interaction.user.send(embed=confirm_embed, file=discord.File("qris.png"))
        except Exception:
            pass
    else:
        try:
            await interaction.user.send(embed=confirm_embed)
        except Exception:
            pass

    await interaction.response.send_message(embed=success_embed("Order submitted! Check your DMs for details."), ephemeral=True)


bot.tree.add_command(premium_slash)


# ─────────────────────────────────────────────
# ═══════════════════════════════════════════
#  PREFIX COMMANDS (OWNER ONLY)
# ═══════════════════════════════════════════
# ─────────────────────────────────────────────

def is_owner():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id == bot.owner_id
    return commands.check(predicate)


# ─────────────────────────────────────────────
# ── MAINTENANCE BROADCAST
# ─────────────────────────────────────────────

@bot.command(name="maintenance")
@is_owner()
async def prefix_maintenance(ctx: commands.Context, *, args: str = ""):
    """
    Usage: !Joy maintenance <title> | <description> | <button_label> | <button_url>
    """
    parts = [p.strip() for p in args.split("|")]
    title       = parts[0] if len(parts) > 0 else "🔧 Maintenance Notice"
    description = parts[1] if len(parts) > 1 else "The bot is undergoing maintenance. Please stand by."
    btn_label   = parts[2] if len(parts) > 2 else "Status Page"
    btn_url     = parts[3] if len(parts) > 3 else "https://status.joycannot.xyz"

    embed = base_embed(f"📢 {title}", description, color=0xF59E0B)
    embed.add_field(name="Sent by", value=str(ctx.author), inline=True)
    embed.add_field(name="Time",    value=discord.utils.format_dt(discord.utils.utcnow(), "f"), inline=True)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=btn_label, url=btn_url, style=discord.ButtonStyle.link))

    success_count = 0
    fail_count    = 0

    await ctx.send(embed=info_embed("📤 Broadcasting...", f"Sending to **{len(bot.guilds)}** servers..."))

    for guild in bot.guilds:
        gc  = guild_cfg(cfg, guild.id)
        ch  = None

        # Try configured main channel first
        if gc.get("main_channel"):
            ch = guild.get_channel(gc["main_channel"])

        # Fallback: system channel, then first writable text channel
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
                success_count += 1
            except Exception:
                fail_count += 1
        else:
            fail_count += 1

        await asyncio.sleep(0.5)  # Rate limit protection

    await ctx.send(embed=success_embed(
        f"Broadcast complete!\n✅ Success: **{success_count}** | ❌ Failed: **{fail_count}**"
    ))


# ─────────────────────────────────────────────
# ── PREMIUM MANAGEMENT (PREFIX / OWNER)
# ─────────────────────────────────────────────

@bot.command(name="premium")
@is_owner()
async def prefix_premium(ctx: commands.Context, action: str = "list", *, args: str = ""):
    """
    !Joy premium list
    !Joy premium add <name> | <duration> | <type> | <price>
    !Joy premium remove <name>
    !Joy premium payment <qris|bank|ewallet> <on|off>
    """
    packages = cfg.get("premium_packages", [])

    if action == "list":
        if not packages:
            await ctx.send(embed=info_embed("💎 Premium Packages", "No packages configured."))
            return
        lines = "\n".join(
            f"• **{p['name']}** — {p['duration']} — {p['type']} — {p['price']}"
            for p in packages
        )
        await ctx.send(embed=info_embed("💎 Premium Packages", lines))

    elif action == "add":
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 4:
            await ctx.send(embed=error_embed("Usage: `!Joy premium add <name> | <duration> | <type> | <price>`"))
            return
        name, duration, pkg_type, price = parts[0], parts[1], parts[2], parts[3]
        packages.append({"name": name, "duration": duration, "type": pkg_type, "price": price})
        cfg["premium_packages"] = packages
        save_config(cfg)
        await ctx.send(embed=success_embed(f"Package **{name}** added!"))

    elif action == "remove":
        name = args.strip()
        before = len(packages)
        cfg["premium_packages"] = [p for p in packages if p["name"].lower() != name.lower()]
        save_config(cfg)
        if len(cfg["premium_packages"]) < before:
            await ctx.send(embed=success_embed(f"Package **{name}** removed!"))
        else:
            await ctx.send(embed=error_embed(f"Package **{name}** not found."))

    elif action == "payment":
        parts  = args.strip().split()
        if len(parts) < 2:
            await ctx.send(embed=error_embed("Usage: `!Joy premium payment <qris|bank|ewallet> <on|off>`"))
            return
        method, state = parts[0].lower(), parts[1].lower()
        if method not in ("qris", "bank", "ewallet") or state not in ("on", "off"):
            await ctx.send(embed=error_embed("Invalid input."))
            return
        cfg["payment_methods"][method] = (state == "on")
        save_config(cfg)
        await ctx.send(embed=success_embed(f"Payment method **{method.upper()}** turned **{state.upper()}**."))

    else:
        await ctx.send(embed=error_embed("Unknown action. Use: `list`, `add`, `remove`, `payment`"))


# ─────────────────────────────────────────────
# ── MAIN CHANNEL CONFIG (PREFIX / OWNER)
# ─────────────────────────────────────────────

@bot.command(name="setchannel")
@is_owner()
async def prefix_setchannel(ctx: commands.Context, guild_id: int, channel_id: int):
    """!Joy setchannel <guild_id> <channel_id> — Set main channel for a specific guild."""
    gc = guild_cfg(cfg, guild_id)
    gc["main_channel"] = channel_id
    save_config(cfg)
    await ctx.send(embed=success_embed(f"Main channel for guild `{guild_id}` set to `{channel_id}`."))


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            embed=error_embed(t(cfg, interaction.guild.id if interaction.guild else 0, "no_perm")),
            ephemeral=True
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            embed=error_embed(f"⏱️ Slow down! Try again in {error.retry_after:.1f}s."),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=error_embed(f"An unexpected error occurred: `{error}`"),
            ephemeral=True
        )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(embed=error_embed("❌ You are not authorized to use this command."))
    elif isinstance(error, commands.CommandNotFound):
        pass  # Silently ignore unknown prefix commands
    else:
        await ctx.send(embed=error_embed(f"Error: `{error}`"))


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
    import logging
logging.basicConfig(level=logging.INFO)
bot.run(token, log_handler=None, reconnect=True)
