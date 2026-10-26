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
- [x] B42 — پنل ادمین ملی مطابق «سند ساختاریافته شناسایی صفحات»
- [x] **انتشار ۳ — مالی و آموزش (بک‌اند کامل، ۲۴۰ تست سبز):**
  B18 کیف پول (ledger + شارژ درگاهی + پرداخت از اعتبار) ·
  B19 کد تخفیف (سقف سروری با قفل ردیفی) ·
  B20 استرداد وجه (چرخه کامل + واریز به کیف پول) ·
  B21 سازمان‌ها (قرارداد + عضویت زمان‌دار) ·
  B22 حسابداری (سند متوازن خودنویس + تسویه) ·
  B23 نظرسنجی/تیکت ·
  B24 داشبورد مدیریتی ·
  B33 CMS (چرخه انتشار + نسخه‌ها) ·
  B34 دوره و درس ·
  B35 فروش و ثبت‌نام دوره ·
  B36 آزمون و گواهی (نمره‌گذاری سروری + استعلام عمومی)
- ردیاب پیشرفت تصویری: `PROGRESS.html` — با هر تغییر به‌روز می‌شود

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
