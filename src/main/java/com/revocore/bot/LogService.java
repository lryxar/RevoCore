package com.revocore.bot;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.channel.concrete.Category;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;

import java.awt.*;
import java.sql.SQLException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class LogService {
    public static final Map<String, String> CHANNELS = new LinkedHashMap<>();

    static {
        CHANNELS.put("general", "لوق-عام");
        CHANNELS.put("messages", "لوق-الرسائل");
        CHANNELS.put("members", "لوق-الدخول-الخروج");
        CHANNELS.put("roles", "لوق-الرتب");
        CHANNELS.put("channels", "لوق-الرومات");
        CHANNELS.put("voice", "لوق-الفويسات");
        CHANNELS.put("names", "لوق-الاسماء");
        CHANNELS.put("automod", "لوق-اوتو-مود");
    }

    private final Database database;

    public LogService(Database database) {
        this.database = database;
    }

    public void ensureLogsLayout(Guild guild, String categoryName) {
        Category category = guild.getCategoriesByName(categoryName, true).stream().findFirst()
                .orElseGet(() -> guild.createCategory(categoryName).complete());

        CHANNELS.forEach((key, name) -> {
            TextChannel channel = category.getTextChannels().stream()
                    .filter(ch -> ch.getName().equalsIgnoreCase(name))
                    .findFirst()
                    .orElseGet(() -> guild.createTextChannel(name, category).complete());
            try {
                database.setGuildSetting(guild.getIdLong(), "log_channel_" + key, channel.getId());
            } catch (SQLException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public TextChannel getLogChannel(Guild guild, String key) {
        try {
            return database.getGuildSetting(guild.getIdLong(), "log_channel_" + key)
                    .map(guild::getTextChannelById)
                    .orElse(null);
        } catch (SQLException e) {
            return null;
        }
    }

    public void logEvent(Guild guild, String type, String title, String description, Member member, String channelText) {
        TextChannel specific = getLogChannel(guild, type);
        TextChannel general = getLogChannel(guild, "general");

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(title)
                .setDescription(description)
                .setColor(new Color(88, 101, 242))
                .setTimestamp(Instant.now())
                .addField("الحدث", title, false);

        if (member != null) {
            embed.addField("العضو", member.getAsMention() + " (`" + member.getId() + "`)", false);
            if (member.getUser().getAvatarUrl() != null) {
                embed.setThumbnail(member.getUser().getAvatarUrl());
            }
        }
        if (channelText != null && !channelText.isBlank()) {
            embed.addField("الروم", channelText, false);
        }

        if (specific != null) specific.sendMessageEmbeds(embed.build()).queue();
        if (general != null && (specific == null || !general.getId().equals(specific.getId()))) {
            general.sendMessageEmbeds(embed.build()).queue();
        }
    }
}
