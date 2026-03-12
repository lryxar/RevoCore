package com.revocore.bot;

import java.sql.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class Database {
    private final Connection connection;

    public Database(String path) throws SQLException {
        this.connection = DriverManager.getConnection("jdbc:sqlite:" + path);
        init();
    }

    private void init() throws SQLException {
        try (Statement stmt = connection.createStatement()) {
            stmt.executeUpdate("""
                    CREATE TABLE IF NOT EXISTS members (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        xp INTEGER NOT NULL DEFAULT 0,
                        level INTEGER NOT NULL DEFAULT 1,
                        last_message_at INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """);
            stmt.executeUpdate("""
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        PRIMARY KEY (guild_id, key)
                    )
                    """);
        }
    }

    public record MemberProgress(int xp, int level, long lastMessageAt) {}
    public record LeaderboardRow(long userId, int level, int xp) {}

    public MemberProgress getOrCreateMember(long guildId, long userId) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT xp, level, last_message_at FROM members WHERE guild_id = ? AND user_id = ?")) {
            ps.setLong(1, guildId);
            ps.setLong(2, userId);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new MemberProgress(rs.getInt(1), rs.getInt(2), rs.getLong(3));
                }
            }
        }

        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO members (guild_id, user_id, xp, level, last_message_at) VALUES (?, ?, 0, 1, 0)")) {
            ps.setLong(1, guildId);
            ps.setLong(2, userId);
            ps.executeUpdate();
        }
        return new MemberProgress(0, 1, 0);
    }

    public void updateMember(long guildId, long userId, int xp, int level, long lastMessageAt) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "UPDATE members SET xp = ?, level = ?, last_message_at = ? WHERE guild_id = ? AND user_id = ?")) {
            ps.setInt(1, xp);
            ps.setInt(2, level);
            ps.setLong(3, lastMessageAt);
            ps.setLong(4, guildId);
            ps.setLong(5, userId);
            ps.executeUpdate();
        }
    }

    public List<LeaderboardRow> getTopMembers(long guildId, int limit) throws SQLException {
        List<LeaderboardRow> rows = new ArrayList<>();
        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT user_id, level, xp FROM members WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?")) {
            ps.setLong(1, guildId);
            ps.setInt(2, limit);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    rows.add(new LeaderboardRow(rs.getLong(1), rs.getInt(2), rs.getInt(3)));
                }
            }
        }
        return rows;
    }

    public void setGuildSetting(long guildId, String key, String value) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT OR REPLACE INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)")) {
            ps.setLong(1, guildId);
            ps.setString(2, key);
            ps.setString(3, value);
            ps.executeUpdate();
        }
    }

    public Optional<String> getGuildSetting(long guildId, String key) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?")) {
            ps.setLong(1, guildId);
            ps.setString(2, key);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return Optional.ofNullable(rs.getString(1));
                }
            }
        }
        return Optional.empty();
    }
}
