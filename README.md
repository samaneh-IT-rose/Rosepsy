# سامانه یکپارچه کلینیک رز (Rose Clinic Platform)

پلتفرم خدمات مشاوره و آموزش روان‌شناسی — پیاده‌سازی بر پایه سند v0.2

## اسناد
| فایل | توضیح |
|---|---|
| `docs/requirements.md` | نیازمندی‌های استخراج‌شده از سند — مرجع واحد اجرا |

## Stack
- Backend: Python / FastAPI
- DB: PostgreSQL
- Web: React / Vite
- Mobile: Flutter (انتشار 2)
- Delivery: Docker + Git + CI/CD

## وضعیت اجرا
- [x] گام 0: نصب PowerShell 7
- [ ] گام 1: بررسی محیط
- [ ] گام 2: اسکلت پروژه + سند نیازمندی‌ها
- [ ] گام 3: راه‌اندازی Git
- [ ] گام 4: تصمیم‌های ADR + تکمیل سند
- [ ] گام 5: اسکلت Backend (FastAPI + docker-compose)

## قراردادهای کاری
- زمان سرور UTC با timestamptz؛ نمایش شمسی فقط در UI
- هر تغییر نیازمندی، اول در `docs/requirements.md` ثبت می‌شود
