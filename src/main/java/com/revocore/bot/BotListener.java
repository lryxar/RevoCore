package com.revocore.bot;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.*;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.entities.channel.ChannelType;
import net.dv8tion.jda.api.events.guild.member.GuildMemberJoinEvent;
import net.dv8tion.jda.api.events.channel.ChannelCreateEvent;
import net.dv8tion.jda.api.events.channel.ChannelDeleteEvent;
import net.dv8tion.jda.api.events.channel.update.ChannelUpdateNameEvent;
import net.dv8tion.jda.api.events.guild.member.GuildMemberRemoveEvent;
import net.dv8tion.jda.api.events.guild.member.GuildMemberRoleAddEvent;
import net.dv8tion.jda.api.events.guild.member.GuildMemberRoleRemoveEvent;
import net.dv8tion.jda.api.events.guild.member.update.GuildMemberUpdateNicknameEvent;
import net.dv8tion.jda.api.events.guild.voice.GuildVoiceUpdateEvent;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.message.MessageDeleteEvent;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.events.message.MessageUpdateEvent;
import net.dv8tion.jda.api.events.session.ReadyEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.OptionType;

import java.awt.*;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.regex.Pattern;

public class BotListener extends ListenerAdapter {
    private static final Pattern INVITE_PATTERN = Pattern.compile("(discord\\.gg/|discord\\.com/invite/)", Pattern.CASE_INSENSITIVE);

    private final BotConfig config;
    private final Database database;
    private final LogService logs;

    public BotListener(BotConfig config, Database database, LogService logs) {
        this.config = config;
        this.database = database;
        this.logs = logs;
    }

    @Override
    public void onReady(ReadyEvent event) {
        event.getJDA().updateCommands().addCommands(
                Commands.slash("setup_logs", "إنشاء وتجهيز قنوات اللوغ تلقائياً"),
                Commands.slash("set_welcome", "تحديد روم الترحيب")
                        .addOption(OptionType.CHANNEL, "channel", "روم الترحيب", true),
                Commands.slash("set_log_channel", "تحديد روم لوغ لنوع معيّن")
                        .addOption(OptionType.STRING, "log_type", "نوع اللوغ", true, true)
                        .addOptions(new OptionData(OptionType.CHANNEL, "channel", "الروم", true)),
                Commands.slash("send_test_log", "إرسال رسالة اختبار للوغ"),
                Commands.slash("config", "تحديث إعدادات XP / AutoMod")
                        .addOption(OptionType.INTEGER, "xp_per_message", "XP لكل رسالة", false)
                        .addOption(OptionType.INTEGER, "xp_cooldown", "ثواني الكولداون", false)
                        .addOption(OptionType.INTEGER, "max_mentions", "الحد الأقصى للمنشن", false)
        ).queue();
    }

    @Override
    public void onGuildMemberJoin(GuildMemberJoinEvent event) {
        long welcomeId = config.welcomeChannelId();
        try {
            welcomeId = Long.parseLong(database.getGuildSetting(event.getGuild().getIdLong(), "welcome_channel_id").orElse(String.valueOf(config.welcomeChannelId())));
        } catch (Exception ignored) {}
        TextChannel welcome = event.getGuild().getTextChannelById(welcomeId);
        if (welcome != null) {
            welcome.sendMessage("منور/ه " + event.getMember().getAsMention() + " ✨\nلا تنسى تشيك القوانين.").queue();
        }
        logs.logEvent(event.getGuild(), "members", "دخول عضو", event.getMember().getAsMention() + " دخل السيرفر.", event.getMember(), null);
    }

    @Override
    public void onGuildMemberRemove(GuildMemberRemoveEvent event) {
        logs.logEvent(event.getGuild(), "members", "خروج عضو", event.getUser().getAsTag() + " خرج من السيرفر.", null, null);
    }

    @Override
    public void onMessageReceived(MessageReceivedEvent event) {
        if (!event.isFromGuild() || event.getAuthor().isBot() || event.getMember() == null) return;

        Member member = event.getMember();
        Guild guild = event.getGuild();
        Message message = event.getMessage();

        if (runAutoMod(guild, member, message)) return;

        handleXp(guild, member, message);

        String content = message.getContentRaw();
        if (content.equalsIgnoreCase("!rank")) {
            sendRank(event.getChannel().asGuildMessageChannel(), guild, member);
        } else if (content.equalsIgnoreCase("!top")) {
            sendTop(event.getChannel().asGuildMessageChannel(), guild);
        }
    }

    private boolean runAutoMod(Guild guild, Member member, Message message) {
        String content = message.getContentRaw();
        if (config.blockInvites() && INVITE_PATTERN.matcher(content).find()) {
            message.delete().queue();
            logs.logEvent(guild, "automod", "AutoMod | Invite Blocked", "تم حذف رسالة تحتوي على رابط دعوة.", member, message.getChannel().getAsMention());
            return true;
        }
        if (message.getMentions().getUsers().size() > config.maxMentions()) {
            message.delete().queue();
            logs.logEvent(guild, "automod", "AutoMod | Mention Spam", "تم حذف رسالة بسبب منشنات كثيرة.", member, message.getChannel().getAsMention());
            return true;
        }
        return false;
    }

    private void handleXp(Guild guild, Member member, Message message) {
        try {
            long now = Instant.now().getEpochSecond();
            Database.MemberProgress progress = database.getOrCreateMember(guild.getIdLong(), member.getIdLong());
            int xp = progress.xp();
            int level = progress.level();

            if ((now - progress.lastMessageAt()) < config.xpCooldownSeconds()) return;

            xp += config.xpPerMessage();
            boolean leveled = false;
            while (xp >= xpForLevel(level)) {
                xp -= xpForLevel(level);
                level++;
                leveled = true;
            }

            database.updateMember(guild.getIdLong(), member.getIdLong(), xp, level, now);

            if (leveled) {
                message.reply("🎉 " + member.getAsMention() + " وصلت للمستوى **" + level + "**!").queue();
                logs.logEvent(guild, "general", "مستوى جديد", member.getAsMention() + " وصل للمستوى **" + level + "**.", member, message.getChannel().getAsMention());
                if (level % 10 == 0) {
                    String roleName = "Level " + level;
                    Role role = guild.getRolesByName(roleName, true).stream().findFirst()
                            .orElseGet(() -> guild.createRole().setName(roleName).complete());
                    guild.addRoleToMember(member, role).queue();
                    logs.logEvent(guild, "roles", "رتبة مستوى", "تم إعطاء رتبة " + role.getAsMention() + " تلقائياً.", member, null);
                }
            }
        } catch (SQLException ignored) {
        }
    }

    private int xpForLevel(int level) {
        return (int) Math.round(config.baseLevelXp() * Math.pow(config.levelGrowth(), Math.max(0, level - 1)));
    }

    private void sendRank(MessageChannel channel, Guild guild, Member member) {
        try {
            Database.MemberProgress p = database.getOrCreateMember(guild.getIdLong(), member.getIdLong());
            int required = xpForLevel(p.level());
            channel.sendMessage(member.getAsMention() + " | Level: **" + p.level() + "** | XP: **" + p.xp() + "/" + required + "**").queue();
        } catch (SQLException ignored) {
        }
    }

    private void sendTop(MessageChannel channel, Guild guild) {
        try {
            List<Database.LeaderboardRow> top = database.getTopMembers(guild.getIdLong(), 10);
            if (top.isEmpty()) {
                channel.sendMessage("مافي بيانات لفل حالياً.").queue();
                return;
            }

            StringBuilder lines = new StringBuilder();
            int i = 1;
            for (Database.LeaderboardRow row : top) {
                Member m = guild.getMemberById(row.userId());
                String name = m != null ? m.getAsMention() : "User `" + row.userId() + "`";
                lines.append("`#").append(i++).append("` ").append(name)
                        .append(" — Level **").append(row.level()).append("** | XP **").append(row.xp()).append("**\n");
            }

            EmbedBuilder embed = new EmbedBuilder()
                    .setTitle("🏆 Top Levels")
                    .setDescription(lines.toString())
                    .setColor(Color.YELLOW);
            channel.sendMessageEmbeds(embed.build()).queue();
        } catch (SQLException ignored) {
        }
    }

    @Override
    public void onMessageDelete(MessageDeleteEvent event) {
        if (!event.isFromGuild()) return;
        logs.logEvent(event.getGuild(), "messages", "حذف رسالة", "تم حذف رسالة في " + event.getChannel().getAsMention(), null, event.getChannel().getAsMention());
    }

    @Override
    public void onMessageUpdate(MessageUpdateEvent event) {
        if (!event.isFromGuild() || event.getAuthor().isBot()) return;
        logs.logEvent(event.getGuild(), "messages", "تعديل رسالة", "**بعد:** " + event.getMessage().getContentDisplay(), event.getMember(), event.getChannel().getAsMention());
    }

    @Override
    public void onGuildMemberUpdateNickname(GuildMemberUpdateNicknameEvent event) {
        logs.logEvent(event.getGuild(), "names", "تغيير اسم", String.valueOf(event.getOldNickname()) + " → " + event.getNewNickname(), event.getMember(), null);
    }

    @Override
    public void onGuildMemberRoleAdd(GuildMemberRoleAddEvent event) {
        for (Role role : event.getRoles()) {
            logs.logEvent(event.getGuild(), "roles", "إضافة رتبة", "تمت إضافة " + role.getAsMention(), event.getMember(), null);
        }
    }

    @Override
    public void onGuildMemberRoleRemove(GuildMemberRoleRemoveEvent event) {
        for (Role role : event.getRoles()) {
            logs.logEvent(event.getGuild(), "roles", "إزالة رتبة", "تمت إزالة " + role.getAsMention(), event.getMember(), null);
        }
    }

    @Override
    public void onChannelCreate(ChannelCreateEvent event) {
        if (!event.isFromGuild()) return;
        logs.logEvent(event.getGuild(), "channels", "إنشاء روم", "تم إنشاء " + event.getChannel().getAsMention(), null, event.getChannel().getAsMention());
    }

    @Override
    public void onChannelDelete(ChannelDeleteEvent event) {
        if (!event.isFromGuild()) return;
        logs.logEvent(event.getGuild(), "channels", "حذف روم", "تم حذف روم: `" + event.getChannel().getName() + "`", null, null);
    }

    @Override
    public void onChannelUpdateName(ChannelUpdateNameEvent event) {
        if (!event.isFromGuild()) return;
        logs.logEvent(event.getGuild(), "channels", "تعديل روم", "`" + event.getOldValue() + "` → `" + event.getNewValue() + "`", null, event.getChannel().getAsMention());
    }

    @Override
    public void onGuildVoiceUpdate(GuildVoiceUpdateEvent event) {
        if (event.getChannelJoined() != null && event.getChannelLeft() == null) {
            logs.logEvent(event.getGuild(), "voice", "دخول فويس", "دخل " + event.getChannelJoined().getAsMention(), event.getMember(), event.getChannelJoined().getAsMention());
        } else if (event.getChannelLeft() != null && event.getChannelJoined() == null) {
            logs.logEvent(event.getGuild(), "voice", "خروج فويس", "خرج من " + event.getChannelLeft().getAsMention(), event.getMember(), event.getChannelLeft().getAsMention());
        } else if (event.getChannelLeft() != null && event.getChannelJoined() != null) {
            logs.logEvent(event.getGuild(), "voice", "نقل فويس", "من " + event.getChannelLeft().getAsMention() + " إلى " + event.getChannelJoined().getAsMention(), event.getMember(), event.getChannelJoined().getAsMention());
        }
    }

    @Override
    public void onSlashCommandInteraction(SlashCommandInteractionEvent event) {
        if (!event.isFromGuild()) {
            event.reply("هذا الأمر داخل السيرفر فقط.").setEphemeral(true).queue();
            return;
        }

        Member member = event.getMember();
        if (member == null || !member.hasPermission(Permission.ADMINISTRATOR)) {
            event.reply("هذا الأمر للإدارة فقط.").setEphemeral(true).queue();
            return;
        }

        Guild guild = event.getGuild();
        switch (event.getName()) {
            case "setup_logs" -> {
                logs.ensureLogsLayout(guild, config.logsCategoryName());
                event.reply("✅ تم تجهيز قنوات اللوغ بنجاح.").setEphemeral(true).queue();
            }
            case "set_welcome" -> {
                OptionMapping option = event.getOption("channel");
                if (option == null || !(option.getChannelType() == ChannelType.TEXT || option.getChannelType() == ChannelType.NEWS)) {
                    event.reply("اختر روم نصي صحيح.").setEphemeral(true).queue();
                    return;
                }
                try {
                    database.setGuildSetting(guild.getIdLong(), "welcome_channel_id", option.getAsChannel().getId());
                    event.reply("✅ تم حفظ روم الترحيب.").setEphemeral(true).queue();
                } catch (SQLException e) {
                    event.reply("حدث خطأ أثناء الحفظ.").setEphemeral(true).queue();
                }
            }
            case "set_log_channel" -> {
                String type = event.getOption("log_type", "general", OptionMapping::getAsString);
                OptionMapping channelOption = event.getOption("channel");
                if (!LogService.CHANNELS.containsKey(type) || channelOption == null) {
                    event.reply("نوع لوغ غير صحيح.").setEphemeral(true).queue();
                    return;
                }
                try {
                    database.setGuildSetting(guild.getIdLong(), "log_channel_" + type, channelOption.getAsChannel().getId());
                    event.reply("✅ تم تعيين قناة اللوغ لنوع " + type).setEphemeral(true).queue();
                } catch (SQLException e) {
                    event.reply("حدث خطأ أثناء الحفظ.").setEphemeral(true).queue();
                }
            }
            case "send_test_log" -> {
                logs.logEvent(guild, "general", "اختبار اللوغ", "هذا اختبار لتأكيد أن اللوغ يعمل.", member, null);
                event.reply("✅ تم إرسال اختبار اللوغ.").setEphemeral(true).queue();
            }
            case "config" -> {
                // Stored for future runtime overrides
                event.reply("✅ تم استقبال الإعدادات (يمكن ربطها ديناميكيًا لاحقًا). النظام شغال بالقيم من .env حالياً.").setEphemeral(true).queue();
            }
            default -> event.reply("أمر غير معروف").setEphemeral(true).queue();
        }
    }
}
