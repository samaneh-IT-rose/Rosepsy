# راهنمای استقرار و نگهداری — انتشار ۱ (B30)

## محیط‌ها (سند §۱۱)
| محیط | هدف | داده |
|---|---|---|
| dev | توسعه روزانه | ساختگی |
| test | CI (postgres+redis+minio) | ساختگی |
| staging | پیش‌تولید و UAT | شبیه تولید |
| prod | سرویس واقعی | فقط با تأیید و لاگ |

## راه‌اندازی dev
1. scripts\env-check.ps1   2. db_sync.py → seed_roles.py → promote_admin.py   3. uvicorn + celery(--pool=solo)

## الزامات تولید (go-live)
- [ ] ENV=prod + OTP_PEPPER قوی (نه پیش‌فرض) + PAYMENT_CALLBACK_ALLOWLIST=IP درگاه
- [ ] TLS/HSTS؛ پورت‌های db/redis/minio منتشر نشوند
- [ ] registry قطعی ایمیج‌ها (mirror ثبت‌شده / خصوصی) — ADR-04
- [ ] uvicorn بدون --reload؛ restart: unless-stopped
- [ ] بکاپ روزانه backup_db.ps1 + تمرین بازیابی فصلی restore_drill.ps1
- [ ] Smoke پس از هر استقرار (سبز <=3min)

## مهاجرت و Rollback
- تازه: db_sync.py | تولید: فقط alembic upgrade head — هرگز create_all
- Rollback: checkout تگ قبلی → build → up → smoke؛ در بدترین حالت بازگردانی بکاپ

## چک‌لیست Quality Gate (§۱۴ خلاصه)
- [ ] pytest کامل سبز + ruff پاک   - [ ] اسکن امنیتی بدون بحرانی/بالا
- [ ] Smoke staging سبز   - [ ] UAT: ورود→رزرو→پرداخت→فاکتور→پرونده→یادداشت
- [ ] drill-log.md به‌روز   - [ ] گزارش denied برای DPO قابل استخراج
