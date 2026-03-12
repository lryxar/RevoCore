package com.revocore.bot;

public record BotConfig(
        String token,
        long welcomeChannelId,
        String logsCategoryName,
        int xpPerMessage,
        int xpCooldownSeconds,
        int baseLevelXp,
        double levelGrowth,
        int maxMentions,
        boolean blockInvites
) {
    public static BotConfig fromEnv() {
        String token = env("DISCORD_TOKEN", "");
        if (token.isBlank()) {
            throw new IllegalStateException("DISCORD_TOKEN is required");
        }
        return new BotConfig(
                token,
                Long.parseLong(env("WELCOME_CHANNEL_ID", "1468823742460330068")),
                env("LOGS_CATEGORY_NAME", "LOGS"),
                Integer.parseInt(env("XP_PER_MESSAGE", "10")),
                Integer.parseInt(env("XP_COOLDOWN_SECONDS", "60")),
                Integer.parseInt(env("BASE_LEVEL_XP", "100")),
                Double.parseDouble(env("LEVEL_GROWTH", "1.15")),
                Integer.parseInt(env("AUTOMOD_MAX_MENTIONS", "5")),
                Boolean.parseBoolean(env("AUTOMOD_BLOCK_INVITES", "true"))
        );
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }
}
