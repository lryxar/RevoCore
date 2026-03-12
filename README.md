# RevoCore Bot

بوت ديسكورد متكامل لتنظيم السيرفر مع نظام ترحيب + مستويات + لوغ احترافي مقسّم.

## أهم المميزات

- ✅ **أوامر عامة بـ `!`** (مثل `!rank` و `!top`).
- ✅ **أوامر الإدارة بـ `/`** (Slash Commands) مع صلاحية Administrator.
- ✅ نظام ترحيب عربي تلقائي.
- ✅ نظام مستويات XP بتدرّج 15٪ لكل مستوى + Anti-Spam cooldown.
- ✅ رتب تلقائية كل 10 مستويات (`Level 10`, `Level 20`, ...).
- ✅ نظام لوغ متقدّم بقنوات منفصلة مثل:
  - `لوق-الرسائل`
  - `لوق-عام`
  - `لوق-الرتب`
  - `لوق-الرومات`
  - `لوق-الفويسات`
  - `لوق-الاسماء`

## المتطلبات

- Python 3.11+
- Bot Token من Discord Developer Portal
- تفعيل Privileged Intents للبوت:
  - Members Intent
  - Message Content Intent

## التشغيل

1. تثبيت المكتبات:

```bash
pip install -r requirements.txt
```

2. نسخ ملف البيئة:

```bash
cp .env.example .env
```

3. تعديل القيم في `.env`.

4. تشغيل البوت:

```bash
python bot.py
```

## أوامر المستخدمين (Prefix)

- `!rank` → يعرض مستواك الحالي وXP.
- `!top` → يعرض ترتيب أعلى 10 أعضاء.

## أوامر الإدارة (Slash)

- `/setup_logs` → إنشاء وتجهيز قنوات اللوغ تلقائيًا تحت تصنيف `LOGS`.
- `/set_welcome` → تحديد روم الترحيب.
- `/set_log_channel` → تحديد روم مخصص لأي نوع لوغ.
- `/send_test_log` → إرسال رسالة اختبار لنظام اللوغ.

## الإعدادات (.env)

- `DISCORD_TOKEN`: توكن البوت (إلزامي).
- `WELCOME_CHANNEL_ID`: آيدي روم الترحيب.
- `LOGS_CATEGORY_NAME`: اسم تصنيف قنوات اللوغ.
- `XP_PER_MESSAGE`: XP لكل رسالة.
- `XP_COOLDOWN_SECONDS`: كولداون XP لمنع السبام.
- `BASE_LEVEL_XP`: XP المطلوب للمستوى الأول.
- `LEVEL_GROWTH`: نسبة نمو صعوبة كل مستوى (الافتراضي 1.15).
