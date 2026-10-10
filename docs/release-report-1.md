# گزارش تحویل انتشار ۱ — هسته عملیاتی (v1.0.0-alpha)

## خلاصه
۱۷ قلم بک‌لاگ کامل + ۳ جزئی (B29/B30/B38) · 165 تست سبز · ۱۳ مهاجرت · ۴۷ جدول در ۷ schema ·
CI سه‌سرویسی · Worker واقعی Outbox (قالب فارسی + retry) · MinIO واقعی (presigned) ·
بکاپ/بازیابی اثبات‌شده (drill-log users 1→1) · Smoke سبز (4x OK).

## Quality Gate (§۱۴)
| معیار | وضعیت |
|---|---|
| Unit+Integration سبز | ✅ |
| مهاجرت‌های ترتیبی بدون شکنندگی | ✅ 0001→0013 |
| اسکن امنیتی | 🔶 Semgrep/Trivy → فاز امنیت |
| Smoke سبز | ✅ |
| UAT امضاشده | ⏳ ذی‌نفع |
| تمرین بازیابی | ✅ users 1→1 در drill-log.md |
| گزارش denied برای DPO | ✅ GET /audit/access |

## پارامترهای بهره‌برداری dev
Hold TTL=600s · OTP: TTL=120s/سقف5/قفل900s/Rate=3&20 per 10min · نشست=7روز · Ticket=60s · Retry=3

## شروع انتشار ۲
خودکارسازی زنجیره paid→جلسه→پرونده (B09↔B15↔B13) + B17 Flutter — پیش‌نیازها آماده‌اند.
