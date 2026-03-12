# RevoCore Bot (Java Edition)

تم تحويل البوت بالكامل إلى **Java + JDA** مع نظام أقوى وأذكى.

## التحسينات الجديدة

- أوامر عامة للأعضاء بـ `!`:
  - `!rank`
  - `!top`
- أوامر إدارة بـ `/` (Admins فقط):
  - `/setup_logs`
  - `/set_welcome`
  - `/set_log_channel`
  - `/send_test_log`
  - `/config`
- نظام XP احترافي مع:
  - Anti-Spam cooldown
  - نمو صعوبة المستوى (`LEVEL_GROWTH`)
  - رتب تلقائية كل 10 مستويات
- نظام Logs متقدم ومقسّم تلقائيًا:
  - `لوق-عام`
  - `لوق-الرسائل`
  - `لوق-الدخول-الخروج`
  - `لوق-الرتب`
  - `لوق-الرومات`
  - `لوق-الفويسات`
  - `لوق-الاسماء`
  - `لوق-اوتو-مود`
- AutoMod ذكي:
  - حظر روابط الدعوات (اختياري)
  - منع Mention Spam
- قاعدة بيانات SQLite لحفظ التقدم والإعدادات.

## المكتبات المستخدمة

- **JDA**: ربط Discord API
- **sqlite-jdbc**: قاعدة البيانات
- **slf4j-simple**: تسجيل السجلات
- **maven-shade-plugin**: بناء Jar جاهز للتشغيل

## المتطلبات

- Java 17+
- Maven 3.9+

## التشغيل

1) انسخ ملف الإعدادات:
```bash
cp .env.example .env
```

2) صدّر المتغيرات من `.env` (لينكس):
```bash
set -a && source .env && set +a
```

3) ابنِ المشروع:
```bash
mvn -q -DskipTests package
```

4) شغّل البوت:
```bash
java -jar target/revocore-bot-1.0.0.jar
```

## هيكل المشروع

- `pom.xml` إعداد Maven وكل المكتبات
- `src/main/java/com/revocore/bot/Main.java` نقطة تشغيل البوت
- `src/main/java/com/revocore/bot/BotConfig.java` تحميل الإعدادات من البيئة
- `src/main/java/com/revocore/bot/Database.java` طبقة SQLite
- `src/main/java/com/revocore/bot/LogService.java` إدارة اللوغ والقنوات
- `src/main/java/com/revocore/bot/BotListener.java` الأحداث + الأوامر + XP + AutoMod

## ملاحظات مهمة

- لازم تفعل intents من Discord Developer Portal:
  - Server Members Intent
  - Message Content Intent
- أول ما تشغل البوت استخدم `/setup_logs` عشان يبني قنوات اللوغ تلقائيًا.
