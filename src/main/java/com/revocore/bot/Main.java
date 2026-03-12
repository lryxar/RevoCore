package com.revocore.bot;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.utils.MemberCachePolicy;
import net.dv8tion.jda.api.utils.cache.CacheFlag;

import java.util.EnumSet;

public class Main {
    public static void main(String[] args) throws Exception {
        BotConfig config = BotConfig.fromEnv();
        Database db = new Database("levels.db");
        LogService logs = new LogService(db);

        JDABuilder builder = JDABuilder.createDefault(config.token())
                .enableIntents(EnumSet.of(
                        GatewayIntent.GUILD_MEMBERS,
                        GatewayIntent.GUILD_MESSAGES,
                        GatewayIntent.GUILD_VOICE_STATES,
                        GatewayIntent.MESSAGE_CONTENT
                ))
                .enableCache(CacheFlag.VOICE_STATE, CacheFlag.MEMBER_OVERRIDES)
                .setMemberCachePolicy(MemberCachePolicy.ALL)
                .addEventListeners(new BotListener(config, db, logs));

        JDA jda = builder.build();
        jda.awaitReady();
        System.out.println("RevoCore Java bot is online: " + jda.getSelfUser().getAsTag());
    }
}
