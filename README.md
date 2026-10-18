# سامانه یکپارچه کلینیک رز (Rose Clinic Platform)

پلتفرم خدمات مشاوره و آموزش روان‌شناسی — پیاده‌سازی بر پایه سند v0.2

## اسناد
| فایل | توضیح |
|---|---|
| `docs/requirements.md` | نیازمندی‌های استخراج‌شده از سند — مرجع واحد اجرا |
| `docs/backlog-status.md` | وضعیت بک‌لاگ B01–B42 و شاخص‌های کلیدی |
| `docs/deferred-items.md` | موارد معوق و تصمیم‌های باز مدیریت |

## Stack
- Backend: Python / FastAPI
- DB: PostgreSQL
- Web: React / Vite
- Mobile: Flutter (انتشار 2)
- Delivery: Docker + Git + CI/CD

## وضعیت اجرا
- [x] گام 0: نصب PowerShell 7
- [x] گام 1: بررسی محیط
- [x] گام 2: اسکلت پروژه + سند نیازمندی‌ها
- [x] گام 3: راه‌اندازی Git
- [x] گام 4: تصمیم‌های ADR + تکمیل سند
- [x] گام 5: اسکلت Backend (FastAPI + docker-compose)
- [x] انتشار ۱ — هسته عملیاتی بک‌اند (B01–B12، B31، B32، B38–B41)
- [x] انتشار ۲ — پرونده دیجیتال، پرسشنامه، جلسات + اپ Flutter (B13–B17)
- [x] B42 — پنل ادمین ملی مطابق «سند ساختاریافته شناسایی صفحات»:
  داشبورد و منوی ۲۹ آیتمی، مدیریت کاربران (فیلتر استانی/شهرستانی، ۱۱ ستون،
  row-drop، ویرایش، ورود به حساب کاربر با ممیزی)، پرونده کاربر (اطلاعات شخصی +
  جدول ۱۲ ستونه خدمات + «بیشتر»)، مراکز و کلینیک‌ها (گروه‌بندی، ایجاد، فیلترها،
  خروجی CSV، جزئیات)، گزارشات (۳ گروه / ۱۰ کارت + گزارش مشاوران با تفکیک
  استانی/سرویس و خروجی CSV)، گزارش فعالیت کاربران — هم API (FastAPI + RBAC +
  ممیزی) و هم UI وب (React RTL فارسی) — ۲۰۰ تست سبز

## اجرای محلی (Backend + دیتابیس)
```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://roz:roz_dev@localhost:5432/roz
.venv/bin/alembic upgrade head                       # 14 مهاجرت
.venv/bin/python -m scripts.seed_admin --admin-phone 09121111111   # داده مرجع سند
.venv/bin/uvicorn app.main:app --port 8000           # API روی /api/v1 + /docs
cd ../web && npm install && npm run dev              # UI وب
# ورود ادمین: OTP با شماره ادمین، سپس مسیر #/admin در وب
```
تست‌ها: `pytest tests/` (نیازمند PostgreSQL + Redis + MinIO/S3)

## قراردادهای کاری
- زمان سرور UTC با timestamptz؛ نمایش شمسی فقط در UI
- هر تغییر نیازمندی، اول در `docs/requirements.md` ثبت می‌شود
