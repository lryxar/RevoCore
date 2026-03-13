import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("revocore")


LOG_CHANNEL_NAMES: dict[str, str] = {
    "general": "لوق-عام",
    "messages": "لوق-الرسائل",
    "members": "لوق-الدخول-الخروج",
    "roles": "لوق-الرتب",
    "channels": "لوق-الرومات",
    "voice": "لوق-الفويسات",
    "names": "لوق-الاسماء",
    "automod": "لوق-اوتو-مود",
    "moderation": "لوق-الادارة",
    "levels": "لوق-اللفل",
}


@dataclass(slots=True)
class BotConfig:
    token: str
    welcome_channel_id: int
    commands_channel_id: int = 1468825356487098430
    logs_category_name: str = "LOGS"

    xp_per_message: int = 12
    xp_cooldown_seconds: int = 45
    level_growth: float = 1.15
    base_level_xp: int = 100

    automod_block_invites: bool = True
    automod_max_mentions: int = 4
    automod_max_caps_ratio: float = 0.75
    automod_duplicate_window_seconds: int = 30

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN is required")

        return cls(
            token=token,
            welcome_channel_id=int(os.getenv("WELCOME_CHANNEL_ID", "1468823742460330068")),
            commands_channel_id=int(os.getenv("COMMANDS_CHANNEL_ID", "1468825356487098430")),
            logs_category_name=os.getenv("LOGS_CATEGORY_NAME", "LOGS"),
            xp_per_message=int(os.getenv("XP_PER_MESSAGE", "12")),
            xp_cooldown_seconds=int(os.getenv("XP_COOLDOWN_SECONDS", "45")),
            level_growth=float(os.getenv("LEVEL_GROWTH", "1.15")),
            base_level_xp=int(os.getenv("BASE_LEVEL_XP", "100")),
            automod_block_invites=os.getenv("AUTOMOD_BLOCK_INVITES", "true").lower() == "true",
            automod_max_mentions=int(os.getenv("AUTOMOD_MAX_MENTIONS", "4")),
            automod_max_caps_ratio=float(os.getenv("AUTOMOD_MAX_CAPS_RATIO", "0.75")),
            automod_duplicate_window_seconds=int(os.getenv("AUTOMOD_DUPLICATE_WINDOW_SECONDS", "30")),
        )


class Database:
    def __init__(self, path: str = "revocore.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                last_message_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (guild_id, key)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                mod_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def member_progress(self, guild_id: int, user_id: int) -> tuple[int, int, int]:
        row = self.conn.execute(
            "SELECT xp, level, last_message_at FROM members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        if row:
            return int(row[0]), int(row[1]), int(row[2])

        self.conn.execute(
            "INSERT INTO members (guild_id, user_id, xp, level, last_message_at) VALUES (?, ?, 0, 1, 0)",
            (guild_id, user_id),
        )
        self.conn.commit()
        return 0, 1, 0

    def save_member_progress(self, guild_id: int, user_id: int, xp: int, level: int, last_message_at: int) -> None:
        self.conn.execute(
            "UPDATE members SET xp = ?, level = ?, last_message_at = ? WHERE guild_id = ? AND user_id = ?",
            (xp, level, last_message_at, guild_id, user_id),
        )
        self.conn.commit()

    def get_top_members(self, guild_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
        rows = self.conn.execute(
            "SELECT user_id, level, xp FROM members WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        return [(int(r[0]), int(r[1]), int(r[2])) for r in rows]

    def set_setting(self, guild_id: int, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (guild_id, key, value),
        )
        self.conn.commit()

    def get_setting(self, guild_id: int, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        ).fetchone()
        return str(row[0]) if row else None

    def add_warning(self, guild_id: int, user_id: int, reason: str, mod_id: int) -> None:
        self.conn.execute(
            "INSERT INTO warnings (guild_id, user_id, reason, mod_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, reason, mod_id, int(time.time())),
        )
        self.conn.commit()

    def warning_count(self, guild_id: int, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        return int(row[0]) if row else 0


def short_text(text: Optional[str], limit: int = 1000) -> str:
    if not text:
        return "*empty*"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def xp_required_for_level(level: int, base_xp: int, growth: float) -> int:
    if level <= 1:
        return base_xp
    return int(round(base_xp * (growth ** (level - 1))))


class RevoCoreBot(commands.Bot):
    def __init__(self, config: BotConfig):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db = Database()
        self.last_message_cache: dict[tuple[int, int], tuple[str, int]] = {}

    async def setup_hook(self) -> None:
        await self.tree.sync()

    def is_commands_channel(self, channel_id: int) -> bool:
        return channel_id == self.config.commands_channel_id

    async def require_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("الأمر داخل السيرفر فقط", ephemeral=True)
            return False
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("هذا الأمر للإدارة فقط (Administrator).", ephemeral=True)
            return False
        return True

    def get_log_channel(self, guild: discord.Guild, key: str) -> Optional[discord.TextChannel]:
        channel_id = self.db.get_setting(guild.id, f"log_channel_{key}")
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if isinstance(ch, discord.TextChannel):
            return ch
        return None

    async def ensure_logs_layout(self, guild: discord.Guild) -> dict[str, discord.TextChannel]:
        category = discord.utils.get(guild.categories, name=self.config.logs_category_name)
        if category is None:
            category = await guild.create_category(name=self.config.logs_category_name, reason="RevoCore logs setup")

        default_overwrite = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
            guild.me: discord.PermissionOverwrite(send_messages=True, view_channel=True),
        }

        created: dict[str, discord.TextChannel] = {}
        for key, name in LOG_CHANNEL_NAMES.items():
            existing = discord.utils.get(category.text_channels, name=name)
            if existing is None:
                existing = await guild.create_text_channel(
                    name=name,
                    category=category,
                    overwrites=default_overwrite,
                    reason="RevoCore logs setup",
                )
            created[key] = existing
            self.db.set_setting(guild.id, f"log_channel_{key}", str(existing.id))
        return created

    async def fetch_audit_actor(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        within_seconds: int = 20,
    ) -> tuple[Optional[discord.User], Optional[str]]:
        if guild.me is None or not guild.me.guild_permissions.view_audit_log:
            return None, None

        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                entry_target_id = getattr(getattr(entry, "target", None), "id", None)
                if target_id is not None and entry_target_id != target_id:
                    continue
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age > within_seconds:
                    continue
                return entry.user, entry.reason
        except discord.Forbidden:
            return None, None
        except discord.HTTPException:
            return None, None

        return None, None

    async def log_event(
        self,
        guild: discord.Guild,
        key: str,
        title: str,
        description: str,
        member: Optional[discord.abc.User] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        actor: Optional[discord.abc.User] = None,
        reason: Optional[str] = None,
        details: Optional[dict[str, str]] = None,
        color: discord.Color = discord.Color.blurple(),
    ) -> None:
        target_specific = self.get_log_channel(guild, key)
        target_general = self.get_log_channel(guild, "general")
        targets = [c for c in [target_specific, target_general] if c is not None]
        unique_targets = list({c.id: c for c in targets}.values())
        if not unique_targets:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="الحدث", value=title, inline=False)

        if member:
            embed.add_field(name="المستهدف", value=f"{member.mention} (`{member.id}`)", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
        if actor:
            embed.add_field(name="المنفذ", value=f"{actor.mention} (`{actor.id}`)", inline=False)
        if channel:
            embed.add_field(name="الروم", value=f"{channel.mention} (`{channel.id}`)", inline=False)
        if reason:
            embed.add_field(name="السبب", value=reason, inline=False)
        if details:
            for name, value in details.items():
                embed.add_field(name=name, value=short_text(value, 1024), inline=False)

        embed.set_footer(text=f"Guild: {guild.id}")

        for target in unique_targets:
            await target.send(embed=embed)


bot = RevoCoreBot(BotConfig.from_env())


async def run_automod(message: discord.Message) -> bool:
    assert message.guild is not None
    cfg = bot.config
    content = message.content

    if cfg.automod_block_invites and ("discord.gg/" in content.lower() or "discord.com/invite/" in content.lower()):
        await message.delete()
        await bot.log_event(
            message.guild,
            "automod",
            "AutoMod | Invite",
            "تم حذف رسالة تحتوي على رابط دعوة.",
            member=message.author,
            channel=message.channel,
            color=discord.Color.red(),
        )
        return True

    if len(message.mentions) > cfg.automod_max_mentions:
        await message.delete()
        await bot.log_event(
            message.guild,
            "automod",
            "AutoMod | Mention Spam",
            "تم حذف رسالة بسبب منشنات كثيرة.",
            member=message.author,
            channel=message.channel,
            details={"المنشنات": str(len(message.mentions))},
            color=discord.Color.red(),
        )
        return True

    letters = [c for c in content if c.isalpha()]
    if letters:
        caps = sum(1 for c in letters if c.isupper())
        ratio = caps / len(letters)
        if ratio > cfg.automod_max_caps_ratio and len(letters) >= 10:
            await message.delete()
            await bot.log_event(
                message.guild,
                "automod",
                "AutoMod | Caps",
                "تم حذف رسالة بسبب استخدام كابس مفرط.",
                member=message.author,
                channel=message.channel,
                details={"caps_ratio": f"{ratio:.2f}"},
                color=discord.Color.red(),
            )
            return True

    key = (message.guild.id, message.author.id)
    now_ts = int(time.time())
    normalized = content.strip().lower()
    last = bot.last_message_cache.get(key)
    if last and last[0] == normalized and now_ts - last[1] <= cfg.automod_duplicate_window_seconds:
        await message.delete()
        await bot.log_event(
            message.guild,
            "automod",
            "AutoMod | Duplicate",
            "تم حذف رسالة مكررة بسرعة.",
            member=message.author,
            channel=message.channel,
            color=discord.Color.red(),
        )
        return True

    bot.last_message_cache[key] = (normalized, now_ts)
    return False


@bot.event
async def on_member_join(member: discord.Member) -> None:
    welcome_id = bot.db.get_setting(member.guild.id, "welcome_channel_id")
    channel = member.guild.get_channel(int(welcome_id)) if welcome_id else member.guild.get_channel(bot.config.welcome_channel_id)
    if isinstance(channel, discord.TextChannel):
        await channel.send(f"منور/ه {member.mention} ✨\nلا تنسى تشيك القوانين.")

    await bot.log_event(member.guild, "members", "دخول عضو", "عضو جديد دخل السيرفر.", member=member, color=discord.Color.green())


@bot.event
async def on_member_remove(member: discord.Member) -> None:
    await bot.log_event(member.guild, "members", "خروج عضو", "عضو غادر السيرفر.", member=member, color=discord.Color.orange())


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return

    if await run_automod(message):
        return

    xp, level, last_ts = bot.db.member_progress(message.guild.id, message.author.id)
    now_ts = int(time.time())

    if now_ts - last_ts >= bot.config.xp_cooldown_seconds:
        xp += bot.config.xp_per_message
        leveled = False
        while xp >= xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth):
            xp -= xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth)
            level += 1
            leveled = True

        bot.db.save_member_progress(message.guild.id, message.author.id, xp, level, now_ts)

        if leveled:
            await message.channel.send(f"🎉 {message.author.mention} وصلت للمستوى **{level}**!")
            await bot.log_event(
                message.guild,
                "levels",
                "مستوى جديد",
                f"وصل للمستوى **{level}**",
                member=message.author,
                channel=message.channel,
                color=discord.Color.gold(),
            )

            if level % 10 == 0 and isinstance(message.author, discord.Member):
                role_name = f"Level {level}"
                role = discord.utils.get(message.guild.roles, name=role_name)
                if role is None:
                    role = await message.guild.create_role(name=role_name, reason="Auto level milestone")
                await message.author.add_roles(role, reason="Level milestone")
                await bot.log_event(
                    message.guild,
                    "roles",
                    "رتبة لفل",
                    f"تم إعطاء رتبة {role.mention}",
                    member=message.author,
                    color=discord.Color.gold(),
                )

    if bot.is_commands_channel(message.channel.id):
        await bot.process_commands(message)



@bot.event
async def on_message_delete(message: discord.Message) -> None:
    if not message.guild:
        return
    author = message.author if message.author and not message.author.bot else None
    await bot.log_event(
        message.guild,
        "messages",
        "حذف رسالة",
        "تم حذف رسالة.",
        member=author,
        channel=message.channel,
        details={"المحتوى": short_text(message.content)},
        color=discord.Color.red(),
    )


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if not before.guild or before.author.bot or before.content == after.content:
        return
    await bot.log_event(
        before.guild,
        "messages",
        "تعديل رسالة",
        "تم تعديل رسالة.",
        member=before.author,
        channel=before.channel,
        details={"قبل": short_text(before.content), "بعد": short_text(after.content)},
        color=discord.Color.yellow(),
    )


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if before.display_name != after.display_name:
        actor, reason = await bot.fetch_audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
        await bot.log_event(
            after.guild,
            "names",
            "تغيير اسم",
            "تم تغيير اسم عضو.",
            member=after,
            actor=actor,
            reason=reason,
            details={"قبل": before.display_name, "بعد": after.display_name},
        )

    if before.timed_out_until != after.timed_out_until:
        actor, reason = await bot.fetch_audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
        timeout_value = after.timed_out_until.isoformat() if after.timed_out_until else "None"
        await bot.log_event(
            after.guild,
            "moderation",
            "تغيير Timeout",
            "تم تعديل حالة التايم اوت.",
            member=after,
            actor=actor,
            reason=reason,
            details={"timed_out_until": timeout_value},
            color=discord.Color.orange(),
        )

    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]

    if added_roles or removed_roles:
        actor, reason = await bot.fetch_audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
        details: dict[str, str] = {}
        if added_roles:
            details["رتب مضافة"] = ", ".join(r.mention for r in added_roles)
        if removed_roles:
            details["رتب محذوفة"] = ", ".join(r.mention for r in removed_roles)
        await bot.log_event(
            after.guild,
            "roles",
            "تحديث رتب عضو",
            "تم تعديل رتب عضو.",
            member=after,
            actor=actor,
            reason=reason,
            details=details,
        )


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel) -> None:
    actor, reason = await bot.fetch_audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
    await bot.log_event(
        channel.guild,
        "channels",
        "إنشاء روم",
        f"تم إنشاء {channel.mention}",
        actor=actor,
        reason=reason,
        channel=channel,
        color=discord.Color.green(),
    )


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
    actor, reason = await bot.fetch_audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    await bot.log_event(
        channel.guild,
        "channels",
        "حذف روم",
        f"تم حذف الروم `{channel.name}`",
        actor=actor,
        reason=reason,
        color=discord.Color.red(),
    )


@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
    details: dict[str, str] = {}
    if before.name != after.name:
        details["الاسم"] = f"{before.name} → {after.name}"
    if hasattr(before, "topic") and hasattr(after, "topic") and getattr(before, "topic") != getattr(after, "topic"):
        details["Topic"] = f"{short_text(getattr(before, 'topic', None), 300)} → {short_text(getattr(after, 'topic', None), 300)}"
    if not details:
        return

    actor, reason = await bot.fetch_audit_actor(after.guild, discord.AuditLogAction.channel_update, after.id)
    await bot.log_event(
        after.guild,
        "channels",
        "تعديل روم",
        "تم تعديل خصائص روم.",
        actor=actor,
        reason=reason,
        channel=after,
        details=details,
        color=discord.Color.yellow(),
    )


@bot.event
async def on_guild_role_create(role: discord.Role) -> None:
    actor, reason = await bot.fetch_audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)
    await bot.log_event(role.guild, "roles", "إنشاء رتبة", f"تم إنشاء رتبة {role.mention}", actor=actor, reason=reason, color=discord.Color.green())


@bot.event
async def on_guild_role_delete(role: discord.Role) -> None:
    actor, reason = await bot.fetch_audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)
    await bot.log_event(role.guild, "roles", "حذف رتبة", f"تم حذف رتبة `{role.name}`", actor=actor, reason=reason, color=discord.Color.red())


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role) -> None:
    details: dict[str, str] = {}
    if before.name != after.name:
        details["الاسم"] = f"{before.name} → {after.name}"
    if before.color != after.color:
        details["اللون"] = f"{before.color} → {after.color}"
    if before.permissions != after.permissions:
        details["الصلاحيات"] = "تم تعديل الصلاحيات"
    if not details:
        return

    actor, reason = await bot.fetch_audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)
    await bot.log_event(
        after.guild,
        "roles",
        "تعديل رتبة",
        f"تم تعديل الرتبة {after.mention}",
        actor=actor,
        reason=reason,
        details=details,
        color=discord.Color.yellow(),
    )


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    if before.channel is None and after.channel:
        await bot.log_event(member.guild, "voice", "دخول فويس", f"دخل {after.channel.mention}", member=member, channel=after.channel)
    elif before.channel and after.channel is None:
        await bot.log_event(member.guild, "voice", "خروج فويس", f"خرج من {before.channel.mention}", member=member, channel=before.channel)
    elif before.channel and after.channel and before.channel != after.channel:
        await bot.log_event(member.guild, "voice", "انتقال فويس", f"من {before.channel.mention} إلى {after.channel.mention}", member=member, channel=after.channel)


@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    if not ctx.guild:
        return
    if ctx.channel.id != bot.config.commands_channel_id:
        await ctx.reply(f"استخدم الأوامر العامة في <#{bot.config.commands_channel_id}> فقط.", mention_author=False)
        return
    xp, level, _ = bot.db.member_progress(ctx.guild.id, ctx.author.id)
    needed = xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth)
    await ctx.send(f"{ctx.author.mention} | Level: **{level}** | XP: **{xp}/{needed}**")


@bot.command(name="top")
async def top(ctx: commands.Context) -> None:
    if not ctx.guild:
        return
    if ctx.channel.id != bot.config.commands_channel_id:
        await ctx.reply(f"استخدم الأوامر العامة في <#{bot.config.commands_channel_id}> فقط.", mention_author=False)
        return
    top_rows = bot.db.get_top_members(ctx.guild.id, 10)
    if not top_rows:
        await ctx.send("مافي بيانات لفل حالياً.")
        return

    lines = []
    for i, (uid, level, xp) in enumerate(top_rows, start=1):
        member = ctx.guild.get_member(uid)
        name = member.mention if member else f"User `{uid}`"
        lines.append(f"`#{i}` {name} — Level **{level}** | XP **{xp}**")

    embed = discord.Embed(title="🏆 Top Levels", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.tree.command(name="setup_logs", description="إنشاء كل قنوات اللوغ تلقائياً")
@app_commands.default_permissions(administrator=True)
async def setup_logs(interaction: discord.Interaction) -> None:
    if not await bot.require_admin(interaction):
        return

    channels = await bot.ensure_logs_layout(interaction.guild)
    details = "\n".join([f"- {k}: {v.mention}" for k, v in channels.items()])
    await interaction.response.send_message(f"✅ تم إعداد اللوغ بالكامل:\n{details}", ephemeral=True)


@bot.tree.command(name="set_welcome", description="تغيير روم الترحيب")
@app_commands.default_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    if not await bot.require_admin(interaction):
        return
    bot.db.set_setting(interaction.guild.id, "welcome_channel_id", str(channel.id))
    await interaction.response.send_message(f"✅ تم تعيين روم الترحيب إلى {channel.mention}", ephemeral=True)


@bot.tree.command(name="set_log_channel", description="ربط نوع لوغ بقناة معينة")
@app_commands.choices(log_type=[app_commands.Choice(name=k, value=k) for k in LOG_CHANNEL_NAMES.keys()])
@app_commands.default_permissions(administrator=True)
async def set_log_channel(interaction: discord.Interaction, log_type: app_commands.Choice[str], channel: discord.TextChannel) -> None:
    if not await bot.require_admin(interaction):
        return

    bot.db.set_setting(interaction.guild.id, f"log_channel_{log_type.value}", str(channel.id))
    await interaction.response.send_message(f"✅ تم تعيين `{log_type.value}` إلى {channel.mention}", ephemeral=True)


@bot.tree.command(name="logs_status", description="عرض حالة إعدادات اللوق")
@app_commands.default_permissions(administrator=True)
async def logs_status(interaction: discord.Interaction) -> None:
    if not await bot.require_admin(interaction):
        return

    lines: list[str] = []
    for key in LOG_CHANNEL_NAMES:
        channel = bot.get_log_channel(interaction.guild, key)
        lines.append(f"- {key}: {channel.mention if channel else 'Not Set'}")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="warn", description="إعطاء تحذير لعضو")
@app_commands.default_permissions(administrator=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
    if not await bot.require_admin(interaction):
        return

    bot.db.add_warning(interaction.guild.id, member.id, reason, interaction.user.id)
    count = bot.db.warning_count(interaction.guild.id, member.id)
    await interaction.response.send_message(f"⚠️ تم تحذير {member.mention}. عدد التحذيرات: **{count}**", ephemeral=True)
    await bot.log_event(
        interaction.guild,
        "moderation",
        "Warn",
        "تم إصدار تحذير إداري.",
        member=member,
        actor=interaction.user,
        details={"السبب": reason, "عدد التحذيرات": str(count)},
        color=discord.Color.orange(),
    )


@bot.tree.command(name="mute", description="توقيت العضو (Timeout)")
@app_commands.default_permissions(administrator=True)
async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 10080],
    reason: str = "No reason",
) -> None:
    if not await bot.require_admin(interaction):
        return

    until = discord.utils.utcnow().timestamp() + (minutes * 60)
    await member.edit(timed_out_until=datetime.fromtimestamp(until, tz=timezone.utc), reason=reason)
    await interaction.response.send_message(f"🔇 تم ميوت {member.mention} لمدة {minutes} دقيقة.", ephemeral=True)
    await bot.log_event(
        interaction.guild,
        "moderation",
        "Mute",
        "تم عمل timeout لعضو.",
        member=member,
        actor=interaction.user,
        reason=reason,
        details={"المدة": f"{minutes} دقيقة"},
        color=discord.Color.orange(),
    )


@bot.tree.command(name="send_test_log", description="اختبار نظام اللوغ")
@app_commands.default_permissions(administrator=True)
async def send_test_log(interaction: discord.Interaction) -> None:
    if not await bot.require_admin(interaction):
        return

    await bot.log_event(
        interaction.guild,
        "general",
        "اختبار",
        "نظام اللوغ يعمل ✅",
        member=interaction.user,
        actor=interaction.user,
        color=discord.Color.green(),
    )
    await interaction.response.send_message("✅ تم إرسال اختبار اللوغ", ephemeral=True)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        return
    await ctx.reply("حدث خطأ أثناء تنفيذ الأمر.", mention_author=False)


if __name__ == "__main__":
    bot.run(bot.config.token)
