import logging
import os
import sqlite3
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
}


@dataclass(slots=True)
class BotConfig:
    token: str
    welcome_channel_id: int
    logs_category_name: str = "LOGS"
    xp_per_message: int = 10
    xp_cooldown_seconds: int = 60
    level_growth: float = 1.15
    base_level_xp: int = 100

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN is required")

        return cls(
            token=token,
            welcome_channel_id=int(os.getenv("WELCOME_CHANNEL_ID", "1468823742460330068")),
            logs_category_name=os.getenv("LOGS_CATEGORY_NAME", "LOGS"),
            xp_per_message=int(os.getenv("XP_PER_MESSAGE", "10")),
            xp_cooldown_seconds=int(os.getenv("XP_COOLDOWN_SECONDS", "60")),
            level_growth=float(os.getenv("LEVEL_GROWTH", "1.15")),
            base_level_xp=int(os.getenv("BASE_LEVEL_XP", "100")),
        )


class LevelStore:
    def __init__(self, db_path: str = "levels.db") -> None:
        self.conn = sqlite3.connect(db_path)
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
        self.conn.commit()

    def get_or_create_member(self, guild_id: int, user_id: int) -> tuple[int, int, int]:
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

    def update_member(self, guild_id: int, user_id: int, xp: int, level: int, last_message_at: int) -> None:
        self.conn.execute(
            """
            UPDATE members
            SET xp = ?, level = ?, last_message_at = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (xp, level, last_message_at, guild_id, user_id),
        )
        self.conn.commit()

    def get_top_members(self, guild_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
        rows = self.conn.execute(
            "SELECT user_id, level, xp FROM members WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        return [(int(r[0]), int(r[1]), int(r[2])) for r in rows]

    def set_guild_setting(self, guild_id: int, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)",
            (guild_id, key, value),
        )
        self.conn.commit()

    def get_guild_setting(self, guild_id: int, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        ).fetchone()
        if not row:
            return None
        return str(row[0])


class LogRouter:
    def __init__(self, store: LevelStore) -> None:
        self.store = store

    async def ensure_logs_layout(self, guild: discord.Guild, category_name: str = "LOGS") -> dict[str, discord.TextChannel]:
        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(name=category_name, reason="RevoCore logs setup")

        channels: dict[str, discord.TextChannel] = {}
        for key, channel_name in LOG_CHANNEL_NAMES.items():
            existing = discord.utils.get(category.channels, name=channel_name)
            if isinstance(existing, discord.TextChannel):
                channels[key] = existing
                continue
            created = await guild.create_text_channel(name=channel_name, category=category, reason="RevoCore logs setup")
            channels[key] = created

        for key, channel in channels.items():
            self.store.set_guild_setting(guild.id, f"log_channel_{key}", str(channel.id))
        return channels

    def get_channel(self, guild: discord.Guild, key: str) -> Optional[discord.TextChannel]:
        stored = self.store.get_guild_setting(guild.id, f"log_channel_{key}")
        if not stored:
            return None
        channel = guild.get_channel(int(stored))
        if isinstance(channel, discord.TextChannel):
            return channel
        return None


def xp_required_for_level(level: int, base_xp: int, growth: float) -> int:
    if level <= 1:
        return base_xp
    return int(round(base_xp * (growth ** (level - 1))))


class RevoCoreBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        intents.voice_states = True

        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.level_store = LevelStore()
        self.log_router = LogRouter(self.level_store)

    async def setup_hook(self) -> None:
        await self.tree.sync()
        LOGGER.info("Slash commands synced.")

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "n/a")

    async def log_event(
        self,
        guild: discord.Guild,
        log_key: str,
        title: str,
        description: str,
        member: Optional[discord.abc.User] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> None:
        targets = [self.log_router.get_channel(guild, log_key), self.log_router.get_channel(guild, "general")]
        targets = [t for t in targets if t is not None]
        if not targets:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if member:
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="العضو", value=f"{member} (`{member.id}`)", inline=False)
        if channel:
            embed.add_field(name="الروم", value=f"{channel.mention} (`{channel.id}`)", inline=False)
        embed.add_field(name="الحدث", value=title, inline=False)

        for target in targets:
            await target.send(embed=embed)


bot = RevoCoreBot(BotConfig.from_env())


@bot.event
async def on_member_join(member: discord.Member) -> None:
    channel = member.guild.get_channel(bot.config.welcome_channel_id)
    if isinstance(channel, discord.TextChannel):
        await channel.send(f"منور/ه {member.mention} ✨\nلا تنسى تشيك القوانين.")

    await bot.log_event(
        guild=member.guild,
        log_key="members",
        title="دخول عضو",
        description=f"{member.mention} دخل السيرفر.",
        member=member,
    )


@bot.event
async def on_member_remove(member: discord.Member) -> None:
    await bot.log_event(
        guild=member.guild,
        log_key="members",
        title="خروج عضو",
        description=f"{member} خرج من السيرفر.",
        member=member,
    )


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    xp, level, last_message_at = bot.level_store.get_or_create_member(guild_id, user_id)
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())

    if now_ts - last_message_at >= bot.config.xp_cooldown_seconds:
        xp += bot.config.xp_per_message
        leveled_up = False
        while xp >= xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth):
            xp -= xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth)
            level += 1
            leveled_up = True

        bot.level_store.update_member(guild_id, user_id, xp, level, now_ts)

        if leveled_up:
            await message.channel.send(f"🎉 {message.author.mention} وصلت للمستوى **{level}**!")
            await bot.log_event(
                guild=message.guild,
                log_key="general",
                title="مستوى جديد",
                description=f"{message.author.mention} وصل للمستوى **{level}**.",
                member=message.author,
                channel=message.channel,
            )
            if level % 10 == 0:
                role_name = f"Level {level}"
                role = discord.utils.get(message.guild.roles, name=role_name)
                if role is None:
                    role = await message.guild.create_role(name=role_name, reason="Auto-created level role")
                if isinstance(message.author, discord.Member):
                    await message.author.add_roles(role, reason="Reached level milestone")
                    await bot.log_event(
                        guild=message.guild,
                        log_key="roles",
                        title="رتبة مستوى",
                        description=f"تم إعطاء رتبة {role.mention} تلقائيًا.",
                        member=message.author,
                    )

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message) -> None:
    if not message.guild or message.author.bot:
        return
    await bot.log_event(
        guild=message.guild,
        log_key="messages",
        title="حذف رسالة",
        description=f"الرسالة: {message.content or '*empty*'}",
        member=message.author,
        channel=message.channel,
    )


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if not before.guild or before.author.bot:
        return
    if before.content == after.content:
        return
    await bot.log_event(
        guild=before.guild,
        log_key="messages",
        title="تعديل رسالة",
        description=f"**قبل:** {before.content or '*empty*'}\n**بعد:** {after.content or '*empty*'}",
        member=before.author,
        channel=before.channel,
    )


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if before.display_name != after.display_name:
        await bot.log_event(
            guild=after.guild,
            log_key="names",
            title="تغيير اسم",
            description=f"{before.display_name} → {after.display_name}",
            member=after,
        )

    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]

    for role in added_roles:
        await bot.log_event(
            guild=after.guild,
            log_key="roles",
            title="إضافة رتبة",
            description=f"تمت إضافة {role.mention}",
            member=after,
        )
    for role in removed_roles:
        await bot.log_event(
            guild=after.guild,
            log_key="roles",
            title="إزالة رتبة",
            description=f"تمت إزالة {role.mention}",
            member=after,
        )


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel) -> None:
    await bot.log_event(channel.guild, "channels", "إنشاء روم", f"{channel.mention} تم إنشاؤه.", channel=channel)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
    await bot.log_event(channel.guild, "channels", "حذف روم", f"`{channel.name}` تم حذفه.")


@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
    if before.name != after.name:
        await bot.log_event(after.guild, "channels", "تعديل روم", f"`{before.name}` → `{after.name}`", channel=after)


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if before.channel is None and after.channel is not None:
        await bot.log_event(member.guild, "voice", "دخول فويس", f"دخل {after.channel.mention}", member=member, channel=after.channel)
    elif before.channel is not None and after.channel is None:
        await bot.log_event(member.guild, "voice", "خروج فويس", f"خرج من {before.channel.mention}", member=member, channel=before.channel)
    elif before.channel != after.channel and before.channel and after.channel:
        await bot.log_event(
            member.guild,
            "voice",
            "نقل فويس",
            f"من {before.channel.mention} إلى {after.channel.mention}",
            member=member,
            channel=after.channel,
        )


# =========================
# Public prefix commands (!)
# =========================
@bot.command(name="rank")
async def rank(ctx: commands.Context) -> None:
    if not ctx.guild or not isinstance(ctx.author, discord.Member):
        return

    xp, level, _ = bot.level_store.get_or_create_member(ctx.guild.id, ctx.author.id)
    needed = xp_required_for_level(level, bot.config.base_level_xp, bot.config.level_growth)
    await ctx.send(f"{ctx.author.mention} | Level: **{level}** | XP: **{xp}/{needed}**")


@bot.command(name="top")
async def top(ctx: commands.Context) -> None:
    if not ctx.guild:
        return
    top_members = bot.level_store.get_top_members(ctx.guild.id, 10)
    if not top_members:
        await ctx.send("مافي بيانات لفل حالياً.")
        return

    lines = []
    for idx, (user_id, level, xp) in enumerate(top_members, start=1):
        user = ctx.guild.get_member(user_id)
        name = user.mention if user else f"User `{user_id}`"
        lines.append(f"`#{idx}` {name} — Level **{level}** | XP **{xp}**")

    embed = discord.Embed(title="🏆 Top Levels", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)


# =========================
# Admin slash commands (/)
# =========================
@bot.tree.command(name="setup_logs", description="إنشاء/تحديث قنوات اللوغ تلقائياً")
@app_commands.default_permissions(administrator=True)
async def setup_logs(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("هذا الأمر داخل السيرفر فقط.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    channels = await bot.log_router.ensure_logs_layout(interaction.guild, bot.config.logs_category_name)

    details = "\n".join(f"- {k}: {v.mention}" for k, v in channels.items())
    await interaction.followup.send(f"✅ تم تجهيز قنوات اللوغ:\n{details}", ephemeral=True)


@bot.tree.command(name="set_welcome", description="تحديد روم الترحيب")
@app_commands.default_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    bot.config.welcome_channel_id = channel.id
    if interaction.guild:
        bot.level_store.set_guild_setting(interaction.guild.id, "welcome_channel_id", str(channel.id))
    await interaction.response.send_message(f"✅ تم تعيين روم الترحيب إلى {channel.mention}", ephemeral=True)


@bot.tree.command(name="set_log_channel", description="تحديد روم لوغ لنوع معيّن")
@app_commands.choices(
    log_type=[
        app_commands.Choice(name="general", value="general"),
        app_commands.Choice(name="messages", value="messages"),
        app_commands.Choice(name="members", value="members"),
        app_commands.Choice(name="roles", value="roles"),
        app_commands.Choice(name="channels", value="channels"),
        app_commands.Choice(name="voice", value="voice"),
        app_commands.Choice(name="names", value="names"),
        app_commands.Choice(name="automod", value="automod"),
    ]
)
@app_commands.default_permissions(administrator=True)
async def set_log_channel(
    interaction: discord.Interaction,
    log_type: app_commands.Choice[str],
    channel: discord.TextChannel,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("هذا الأمر داخل السيرفر فقط.", ephemeral=True)
        return

    bot.level_store.set_guild_setting(interaction.guild.id, f"log_channel_{log_type.value}", str(channel.id))
    await interaction.response.send_message(
        f"✅ تم تعيين لوغ `{log_type.value}` إلى {channel.mention}",
        ephemeral=True,
    )


@bot.tree.command(name="send_test_log", description="إرسال رسالة اختبار على نظام اللوغ")
@app_commands.default_permissions(administrator=True)
async def send_test_log(interaction: discord.Interaction) -> None:
    if not interaction.guild or not interaction.user:
        await interaction.response.send_message("هذا الأمر داخل السيرفر فقط.", ephemeral=True)
        return

    await bot.log_event(
        guild=interaction.guild,
        log_key="general",
        title="اختبار اللوغ",
        description="هذا اختبار لتأكيد أن نظام اللوغ يعمل بشكل صحيح.",
        member=interaction.user,
    )
    await interaction.response.send_message("✅ تم إرسال اختبار اللوغ.", ephemeral=True)


if __name__ == "__main__":
    bot.run(bot.config.token)
