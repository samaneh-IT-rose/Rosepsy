# نیازمندی‌های سامانه یکپارچه کلینیک رز (roz)

- **مبدأ:** `doc_requimentt_v02.html` — سند جامع v0.2
- **نسخه این فایل:** v0.3 — استخراج کامل به‌جز موارد بند 0
- **کاربرد:** مرجع واحد اجرا؛ هر تغییر نیازمندی اول اینجا ثبت می‌شود

---

## 0) وضعیت استخراج سند
دریافت‌شده: بخش‌های 01–07 (تا نام فرایند 05) · 08b · 09a · 10 · 11 · 12 · 13 · 14 · 15 · 16 · 17 · 18
**هنوز دریافت‌نشده:**
- [ ] انتهای دیاگرام BPMN فرایند 05
- [ ] نام و دیاگرام BPMN فرایند 06 و 07
- [ ] بخش 08a (وایرفریم صفحات) — اگر در سند وجود دارد

تذکر: بخش 18 سند (۲۴ پرامپت AI) راهنمای ابزار است؛ نیازمندی ساخت نیست — ما خودِ پیاده‌سازی را انجام می‌دهیم.

## 1) نام‌گذاری رسمی طبق سند (بخش 11)
- دامنه: `roz-clinic.ir`
- مخازن: `roz-backend` (FastAPI/Alembic/تست) · `roz-web` (React/Vite) · `roz-mobile` (Flutter) · `roz-infra` (Compose/استقرار/بکاپ) · `roz-docs` (ADR/BPMN/API)
- الگوی Git: `main`, `develop`, `release/*`, `feature/*`, `hotfix/*` · Conventional Commits · هر PR حداقل یک بازبین + CI سبز · Semantic Versioning
- پوشه محلی فعلی: `D:\projects\rose-clinic` — فقط محل استقرار؛ آرتیفکت‌های داخلی با نام‌گذاری سند (roz) ساخته می‌شوند

## 2) هدف محصول
پلتفرم واحد خدمات کلینیک رز: رزرو و پرداخت، پرونده دیجیتال محرمانه، پیام‌رسانی امن، آموزش (دوره/آزمون/گواهی)، تست روان‌شناسی با تفسیر مصوب، CMS و نقشه شعب، گزارش مدیریتی، AI فقط کمکی تحت نظارت متخصص.

## 3) فناوری‌های الزامی + پیش‌فرض‌های صریح سند
| لایه | الزام / پیش‌فرض سند |
|---|---|
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 · OpenAPI از کد · صف پس‌زمینه · الگوی Outbox برای رویداد مالی/اعلانی · request-id + لاگ ساختاریافته + health check |
| Database | PostgreSQL 16 · schemaها: `core, booking, clinical, finance, content, edu, audit` · timestamptz/UTC · قید ضد رزرو متداخل و ثبت مالی تکراری · نسخه‌گذاری تعرفه/محتوا/آزمون/تفسیر/رضایت |
| Queue | Celery + Redis (بخش 11 و 18 سند) |
| Storage | MinIO / S3-compatible — فایل هرگز در DB نیست (بخش 18) |
| Frontend | React 18 + Vite + TypeScript + TanStack Query · RTL فارسی · شمسی فقط در UI |
| Mobile | Flutter 3 (اپ مراجع، انتشار 2) · API مشترک نسخه‌دار |
| CI/CD | GitHub Actions (بخش 18) · Docker + docker-compose |
| شناسه | UUID v7 (بخش 18) · UTC در DB، شمسی در UI |

⚠️ Python محلی شما 3.13.15 است — سازگار؛ ایمیج رسمی Docker طبق سند 3.12.

## 4) وضعیت ADRها
| کد | موضوع | وضعیت |
|---|---|---|
| ADR-01 | نوع شناسه | پیش‌فرض سند: UUID v7 (§18) — فایل ADR رسمی پس از تأیید |
| ADR-02 | صف کار | پیش‌فرض سند: Celery + Redis (§11, §18) |
| ADR-03 | احراز هویت وب | سند §10: Bearer + نشست HttpOnly + CSRF double-submit |
| ADR-04 | ذخیره فایل | پیش‌فرض سند: MinIO / S3-compatible (§11) |
| ADR-05 | درگاه پرداخت | باز → تصمیم D02 |
| ADR-06 | سرویس نقشه | باز → تصمیم D03 |
| ADR-07 | رندر عمومی | باز |
| ADR-08 | مشاهده‌پذیری | باز |

## 5) نقشه راه انتشارها (جمع 865 نفرروز طبق سند — اختلاف 8 نفرروز بسته شد: با اعداد سند)
| انتشار | محدوده | نتیجه |
|---|---|---|
| 1 هسته عملیاتی | B01–B12؛ B31,B32,B38,B39,B40,B41؛ سهمی از B29,B30 | مرکز/شعب، خدمت و مشاور، تقویم، رزرو، پرداخت، فاکتور، پیام اولیه، فایل امن، نقشه |
| 2 خدمات حرفه‌ای | B13–B17 | پرونده دیجیتال، رضایت، پرسشنامه، جلسات، اپ Flutter |
| 3 مالی و آموزش | B18–B24، B33–B36 | کیف پول، تخفیف، استرداد، سازمان، حسابداری، گزارش، دوره/آزمون/گواهی |
| 4 ارزیابی و AI | B25,B26,B37 | تست نسخه‌دار، AI تحت نظارت |
| 5 بلوغ داده | B27,B28 | ML ارزیابی‌شده، یکپارچه‌سازی بیرونی |

## 6) چرخه عمر موجودیت‌ها — State Machines (بخش 09a سند) ⭐
- `appointments`: hold → pending_payment → confirmed → in_progress → completed ‖ cancelled · no_show · expired
- `orders`: draft → awaiting_payment → paid ‖ failed · cancelled · refunded
- `refund_requests`: submitted → reviewing → approved → executed ‖ rejected
- `files`: uploaded → scanning → clean ‖ quarantined · deleted
- `course_enrollments`: invited → pending_payment → active → completed ‖ expired · revoked
- `psych_attempts`: started → consented → in_progress → scored → reviewed ‖ abandoned
- `consents`: draft → granted ‖ revoked
- `contents`: draft → in_review → published ‖ archived · rejected

جریان جمع‌آوری داده (8 مرحله): بازدید(IP/دستگاه/موضوعات) → ورود(موبایل/OTP هش/دستگاه) → رزرو و پرداخت(خدمت/اسلات/مبلغ/مرجع درگاه) → رضایت و پرونده(نسخه رضایت/پرسشنامه/ریسک) → جلسه(زمان/حضور/یادداشت/ارجاع) → آموزش(دوره/پیشرفت/نتیجه/گواهی) → ارزیابی(نسخه تست/پاسخ/مقیاس/تفسیر ناظر) → پیگیری(نظرسنجی/شکایت/رضایت تبلیغاتی/رخداد دسترسی)

## 7) قرارداد API (بخش 10 سند) ⭐
**اصول:** پیشوند `/api/v1`؛ تغییر شکننده فقط با نسخه جدید · Bearer + نشست HttpOnly با CSRF double-submit برای وب · پاکت پاسخ `{data, meta, errors}` با کد ماشینی و پیام فارسی · صفحه‌بندی cursor-based · `Idempotency-Key` برای عملیات مالی و رزرو · Rate limit بر اساس نقش/endpoint؛ 429 با Retry-After

| متد | مسیر | نقش |
|---|---|---|
| POST | /api/v1/auth/otp/request | عمومی (نرخ‌محدود موبایل+IP) |
| POST | /api/v1/auth/otp/verify | عمومی |
| GET | /api/v1/me | کاربر |
| GET | /api/v1/public/branches | عمومی (فیلتر شهر) |
| GET | /api/v1/public/branches/nearby | عمومی (بدون ذخیره مکان) |
| GET | /api/v1/services | کاربر |
| GET | /api/v1/consultants/{id}/availability | کاربر |
| POST | /api/v1/booking-holds | کاربر |
| POST | /api/v1/appointments | کاربر |
| POST | /api/v1/orders | کاربر + Idempotency-Key |
| POST | /api/v1/payments/start | کاربر |
| POST | /api/v1/payments/callback | درگاه (فقط IP درگاه) |
| GET | /api/v1/invoices/{id} | مالک/مالی |
| GET | /api/v1/invoices/{id}.pdf | مالک/مالی |
| POST | /api/v1/files/upload-intents | کاربر |
| POST | /api/v1/files/{id}/complete | کاربر |
| GET | /api/v1/files/{id}/download-ticket | مالک |
| POST | /api/v1/courses/{id}/enrollments | کاربر |
| GET | /api/v1/courses/{id}/lessons/{lid}/stream | ثبت‌نام‌کرده (توکن موقت) |
| POST | /api/v1/course-attempts/{id}/submit | ثبت‌نام‌کرده (نمره سمت سرور) |
| GET | /api/v1/my-certificates | کاربر |
| POST | /api/v1/psych-attempts | کاربر (با رضایت) |
| POST | /api/v1/psych-attempts/{id}/submit | کاربر |
| GET | /api/v1/me/psych-results | کاربر |
| POST | /api/v1/refund-requests | کاربر |
| POST | /api/v1/refunds/{id}/approve | مالی |
| GET | /api/v1/dashboards/manager | مدیر |
| GET | /api/v1/audit/access | DPO |

## 8) DevOps (بخش 11 سند)
- **پایپلاین:** Lint → Unit → Integration → Build → Container Scan → Push → Deploy Staging → Smoke → Manual Approve → Deploy Prod
- **محیط‌ها:** dev(تیم فنی/داده ساختگی) · test(CI) · staging(ذی‌نفعان/شبیه تولید) · prod(فقط با تأیید و لاگ)
- **بکاپ:** کامل روزانه PostgreSQL با نگهداری 30 روز · افزایشی فایل‌ها · تمرین بازیابی فصلی · RPO≤1h · RTO≤4h
- **compose سند:** db(postgres:16-alpine) · redis(7-alpine) · minio · api(uvicorn --reload) · worker(celery) · web(npm dev)

## 9) امنیت (بخش 12 سند) — قواعد کلیدی ⭐
- TLS اجباری + HSTS؛ هش با **Argon2id**؛ توکن با انقضای کوتاه و چرخش
- **OTP: انقضای ۲ دقیقه، سقف ۵ تلاش، قفل موقت پس از تلاش‌های ناموفق**
- CSRF double-submit؛ Rate limit چندلایه (IP/کاربر/نشست/endpoint)؛ کنترل‌های OWASP Top10 (IDOR/SSRF/XSS/SQLi)
- اسکن وابستگی و تصویر کانتینر در CI؛ رد آسیب‌پذیری بحرانی
- **هر خواندن داده درمانی در audit_logs**؛ مجوز هر مسیر با permission (RBAC + ABAC سبک + scope شعبه)؛ تست خودکار ماتریس دسترسی در هر PR
- فایل: URL کوتاه‌مدت امضاشده؛ آنتی‌ویروس + قرنطینه؛ حذف متادیتای تصاویر؛ ممنوعیت اجرای اسکریپت از مسیر عمومی
- AI: بدون رضایت صریح، متن درمانی به سرویس بیرونی نمی‌رود؛ لاگ درخواست/پاسخ AI؛ تأیید انسانی اجباری

**طبقه‌بندی داده:** عمومی(پروفایل عمومی/شعبه) · محرمانه(پروفایل و تماس: مالک+نقش مجاز | رزرو و پرداخت: مالک+مالی+حسابرسی رخداد) · بسیار حساس(یادداشت درمانی: مشاور مجاز+DPO+لاگ | نتیجه تست: مالک+ناظر علمی+لاگ | رضایت: تغییرناپذیری+ابطال با حفظ سابقه)

## 10) اسپرینت‌های انتشار 1 — دو هفته‌ای، 16 هفته (بخش 13 سند)
| S | Story (خلاصه) | بک‌لاگ |
|---|---|---|
| S1 | محیط توسعه پایدار (Docker بالا، CI سبز، مستند راه‌اندازی) | B01 |
| S2 | ورود موبایل با OTP (انقضا/سقف تلاش) | B02 |
| S3 | ثبت متقاضی توسط پذیرش | B03, B04 |
| S4 | تعریف مشاور و خدمت | B05, B06, B31 |
| S5 | تعرفه نسخه‌دار | B07, B32 |
| S6 | تقویم و مرخصی مشاور | B08 |
| S7 | رزرو نوبت (Hold/انقضا/عدم تعارض) | B09 |
| S8 | پرداخت و فاکتور | B10, B11 |
| S9 | اعلان‌ها | B12, B38 |
| S10 | فایل امن | B39 |
| S11 | نقشه شعب | B40 |
| S12 | رضایت و کنترل دسترسی | B41 |
| S13 | پرونده و رضایت | B13, B14 |
| S14 | یادداشت جلسه | B15, B16 |
| S15 | اپ موبایل | B17 |
| S16 | تحویل انتشار 1 (UAT/بکاپ/مستند) | B29, B30 |

## 11) آزمون — 12 دسته (بخش 14 سند)
| # | دسته | ابزار | معیار قبولی | زمان |
|---|---|---|---|---|
| 1 | Unit | pytest, hypothesis, Vitest, flutter_test | پوشش ≥75% ماژول حیاتی؛ main سبز | هر Commit |
| 2 | Integration | pytest + testcontainers (PG/Redis/MinIO) | تراکنش حساس اتمیک؛ rollback در خطا | هر PR |
| 3 | Contract | OpenAPI diff, Schemathesis, Dredd | بدون تغییر شکننده بدون نسخه جدید | هر PR + انتشار |
| 4 | E2E | Playwright, flutter integration_test | سناریوهای P0 سبز در staging | شبانه + قبل انتشار |
| 5 | Security | ZAP, Semgrep, Trivy, Bandit | بدون بحرانی/بالا؛ ماتریس دسترسی 100% | PR سبک + ماهانه + قبل انتشار |
| 6 | Perf/Load | k6, Locust, JMeter | p95<500ms در 100 کاربر هم‌زمان؛ بدون 5xx پایدار | هفتگی staging |
| 7 | Accessibility | axe-core, Lighthouse, NVDA | بدون خطای بحرانی axe؛ ناوبری کیبورد کامل | هر انتشار |
| 8 | UAT | سناریو کتبی + چک‌لیست | امضای ذی‌نفع روی سناریوهای بحرانی | پایان هر انتشار |
| 9 | Regression | E2E + smoke برچسب‌دار | 100% سبز قبل انتشار | قبل هر انتشار |
| 10 | Smoke | curl + Playwright سریع | سبز در ≤3 دقیقه پس از استقرار | بعد هر Deploy |
| 11 | Compliance/Privacy | گزارش audit، تست ابطال رضایت | بدون داده درمانی بدون رضایت؛ گزارش دسترسی کامل | هر انتشار |
| 12 | Backup Drill | اسکریپت بازیابی + محیط ایزوله | RTO≤4h، RPO≤1h، گزارش امضاشده | فصلی + قبل انتشار بزرگ |

**پوشش تست بر بک‌لاگ (✓=اجباری):** B02(Unit/Int/E2E/Sec/Perf/UAT) · B04(Unit/Int/Sec/UAT) · B07(Unit/Int/E2E/UAT) · B09,B10(Unit/Int/E2E/Sec/Perf/UAT) · B13(Unit/Int/E2E/Sec/UAT) · B35,B36,B37,B39,B41(Unit/Int/E2E/Sec/UAT)

**Quality Gate:** Unit+Integration سبز · schema diff بدون شکنندگی · اسکن امنیتی بدون بحرانی/بالا · پوشش ≥75% ماژول حیاتی · E2E پ0 سبز در staging · UAT امضاشده · گزارش بازیابی به‌روز · دسترس‌پذیری بدون بحرانی

## 12) زمان و هزینه (بخش 15 سند) — جمع 865 نفرروز
Backend 345 (40%) · Frontend وب 195 (23%) · Flutter 50 (6%) · DevOps 60 (7%) · UI/UX 60 (7%) · QA 90 (10%) · امنیت 35 (4%) · مستندسازی 30 (3%)
هزینه‌های جاری جداگانه: سرور، پیامک/ایمیل/Push، درگاه، فضای ذخیره/CDN، نقشه، پایش، SSL/دامنه، نگهداری 12–18٪ سالانه

## 13) تصمیم‌های باز مدیریتی (بخش 16 سند)
| کد | موضوع | گزینه‌ها |
|---|---|---|
| D01 | دامنه دقیق انتشار 1 | حفظ/کاهش/گسترش |
| D02 | درگاه پرداخت | زرین‌پال / آیدی‌پی / بانکی مستقیم |
| D03 | سرویس نقشه | Map.ir / Neshan / OSM |
| D04 | سرویس پیامک | کاوه‌نگار / فراز / ملی‌پیامک |
| D05 | میزبانی | ابر داخلی / سرور اختصاصی / ترکیبی |
| D06 | نگهداری داده درمانی | 5 سال / 10 سال / مصوبه |
| D07 | AI | داخلی / بیرونی / تعطیل |
| D08 | ناظر علمی تست‌ها | فرد / کمیته |
| D09 | تیم اجرا | درون‌سازمانی / برون‌سپاری / ترکیبی |
| D10 | مالکیت کد | واگذاری کامل / لایسنس |

## 14) تحویل‌دادنی‌ها (بخش 17 سند)
فنی: کد+تست+OpenAPI · Docker/Compose محیط‌ها · Migration و seed · CI/CD و تنظیمات امنیتی · ADRها · BPMN به‌روز
محصولی: نیازمندی نهایی · طراحی UI · راهنمای نقش‌ها · راهنمای بازیابی · گزارش 12 دسته آزمون · UAT امضاشده · آموزش · SLA
**پذیرش نهایی:** فقط با Quality Gate سبز + گزارش بازیابی + تأیید مسیرهای P0 در پیش‌تولید

## 15) نقش‌ها (خلاصه)
بازدیدکننده(عمومی) · مراجع/خریدار(فقط داده خود) · مشاور(پرونده مراجعان مجاز؛ نه همه) · پذیرش(بدون یادداشت درمانی) · مدیر شعبه(محدود به شعبه) · مدیر محتوا/آموزش(بدون داده درمانی) · مالی(بدون جزئیات جلسه) · مدیر سامانه(بدون دسترسی درمانی پیش‌فرض) · ناظر علمی(انتشار فقط با نسخه/تاریخچه) · حسابرس/DPO(بدون متن درمانی)

**قواعد سراسری:** فیلد=ضروری/سقف/قالب/یکتایی/پیام خطا · زمان سرور منبع حقیقت · موبایل نرمال واحد · ویرایش موجودیت منتشرشده داده تاریخی را خراب نکند · وضعیت‌های قابل انتقال مستند · حذف داده درمانی فقط با سیاست مصوب + رخداد
**سه مفهوم متفاوت:** پرسشنامه پرونده(B14) ≠ آزمون دوره(B36) ≠ تست روان‌شناسی(B37)

## 16) بک‌لاگ B01–B30 (جمع 612 نفرروز)
| کد | قابلیت | API / جدول | قاعده و پذیرش کلیدی | وابستگی | اولویت·نفرروز |
|---|---|---|---|---|---|
| B01 | پوسته، تنظیمات، وضعیت سرویس، خطا | /health /ready؛ app_settings | استقرار تکرارپذیر؛ ردیابی خطا با request-id | — | P0·18 |
| B02 | ورود OTP و پروفایل | /auth/* /me؛ users, profiles, otp_challenges, auth_sessions | انقضا و سقف تلاش OTP؛ کد مصرف‌شده دوباره پذیرفته نشود | B01 | P0·20 |
| B03 | ثبت و جست‌وجوی متقاضی | /applicants؛ applicants | ثبت فاقد حساب توسط پذیرش؛ بررسی تکراری | B02,B04 | P0·12 |
| B04 | نقش، محدوده شعبه، گزارش دسترسی | /roles /users/{id}/roles | رد و ثبت دسترسی غیرمجاز در API | B02 | P0·15 |
| B05 | پروفایل مشاور | /consultants /verification-reviews؛ consultants, credentials | بدون صلاحیت معتبر در فهرست رزرو نیست | B04,B39 | P0·20 |
| B06 | خدمت، تخصص، مدت، نوع جلسه | /services /specialties؛ services, specialties | مدت مثبت؛ خدمت غیرفعال رزرو جدید نگیرد | B04 | P0·15 |
| B07 | تعرفه نسخه‌دار | /tariffs /pricing/quote؛ tariffs, tariff_versions | رد هم‌پوشانی ناسازگار؛ قیمت گذشته ثابت | B06 | P0·16 |
| B08 | تقویم، برنامه هفتگی، استثنا | /availability /availability-rules | فقط زمان واقعاً آزاد و منطبق با خدمت | B05,B06,B31 | P0·24 |
| B09 | hold موقت، نوبت، تغییر/لغو | /booking-holds /appointments؛ appointments, slot_claims | دو رزرو ناسازگار قطعی نشود؛ hold منقضی آزاد شود | B03,B07,B08 | P0·27 |
| B10 | سفارش، پرداخت، درگاه | /orders /payments/*؛ orders, payments | قطعی فقط با تأیید سرور؛ callback تکراری بی‌اثر | B07,B09 | P0·26 |
| B11 | فاکتور و PDF | /invoices/*؛ invoices, invoice_items | مبلغ = snapshot سفارش؛ شماره یکتا | B10 | P0·14 |
| B12 | مرکز اعلان رویدادی | /notifications؛ notifications, notification_events | شکست اعلان، پرداخت را برگشت نزند | B02,B09,B10 | P0·12 |
| B13 | پرونده دیجیتال، رضایت‌ها | /clinical-records /consents | هر خواندن درمانی: مجوز + حسابرسی | B03,B04,B39 | P0·30 |
| B14 | سازنده پرسشنامه، نسخه | /questionnaires /submissions | تغییر فرم، پاسخ نسخه قبل را تغییر ندهد | B13 | P0·18 |
| B15 | جلسه، یادداشت، ارجاع | /encounters /notes | یادداشت تأییدشده بدون ردپای اصلاح بازنویسی نشود | B09,B13 | P0·22 |
| B16 | اتاق انتظار، حضور، پایش | /sessions/* | پایش جدا از دسترسی به محتوای محرمانه | B09,B04 | P0·20 |
| B17 | اپ Flutter | API مشترک؛ ذخیره حداقلی | مسیر اصلی + قطع اینترنت آزمون شود | B02,B09,B10,B13 | P1·35 |
| B18 | کیف پول | /wallet/*؛ wallets, wallet_entries | مانده=جمع گردش؛ دوباره‌مصرفی ممنوع | B10 | P1·20 |
| B19 | کد تخفیف | /discounts/*؛ discounts, discount_redemptions | مصرف هم‌زمان بیش از سقف ممنوع | B07,B10 | P1·12 |
| B20 | استرداد | /refunds/*؛ refund_requests, refunds | بیش از مجاز و اجرای تکراری ممنوع | B10,B18 | P1·16 |
| B21 | سازمان و قرارداد | /organizations/* | عضویت هنگام خدمت معتبر؛ سازمان به یادداشت دسترسی نگیرد | B03,B07 | P1·22 |
| B22 | حسابداری، تسویه، مغایرت | /journal-entries /settlements | سند متوازن و ردپذیر به رویداد مالی | B10,B18,B20 | P1·34 |
| B23 | نظرسنجی، شکایت، تیکت | /survey-responses /support-tickets | شکایت بدون افشای پرونده به پشتیبان | B02,B09 | P1·13 |
| B24 | داشبورد و گزارش | /dashboards/* /reports/* | KPI شفاف؛ تطبیق با داده مالی | B09,B10,B22 | P1·22 |
| B25 | پیشنهاد مشاور با دلیل | /ai/consultant-recommendations | صلاحیت و دسترس‌پذیری قبل رتبه‌بندی | B05,B06,B08 | P1·14 |
| B26 | خلاصه/پیش‌نویس AI | /ai/summaries /ai/note-drafts | ورود به یادداشت نهایی فقط با تأیید متخصص | B13,B15 | P2·32 |
| B27 | ML: داده، مدل، ارزیابی | /ml/models /ml/evaluations | انتشار بدون ارزیابی کارایی/سوگیری ممنوع | B25,B26 | P2·25 |
| B28 | یکپارچه‌سازی و کمپین | /integrations/channels /campaigns | داده درمانی به شبکه اجتماعی نرود | B38 | P2·9 |
| B29 | امنیت، بکاپ، ممیزی | سیاست، لاگ، بکاپ | بکاپ واقعاً بازیابی و آزمون شود | سراسری | P0/P1·24 |
| B30 | QA، پیش‌تولید، تحویل | تست خودکار، UAT، rollback | رزرو تا فاکتور در staging بازتولیدپذیر | سراسری | P0/P1·25 |

## 17) بک‌لاگ B31–B41 (جمع 245 نفرروز)
| کد | قابلیت | API / جدول | قاعده و پذیرش کلیدی | وابستگی | اولویت·نفرروز |
|---|---|---|---|---|---|
| B31 | مراکز و شعب | /clinics /clinics/{id}/branches؛ clinics, branches, branch_service_offerings | slug یکتا؛ lat∈[-90,90]؛ lon∈[-180,180]؛ شعبه منتشرنشده عمومی نیست؛ خدمت ناموجود نمایش داده نشود | B01,B04,B06 | P0·18 |
| B32 | دسته‌بندی موضوعی | /topics /public/topics؛ topics, content_topics | والد چرخه‌ای ممنوع؛ موضوع دارای محتوا حذف فیزیکی نشود | B04 | P0·8 |
| B33 | مقاله/خبر/پادکست/ویدئو | /contents /public/contents؛ contents, content_revisions | پیش‌نویس عمومی نیست؛ انتشار فقط با نقش ناشر؛ تاریخچه تغییر | B32,B39 | P1·23 |
| B34 | دوره و درس | /courses /courses/{id}/modules /lesson-progress | رایگان=صفر، پولی=مثبت؛ انتشار با حداقل یک درس؛ نسخه درس منتشرشده حفظ شود | B32,B39 | P1·33 |
| B35 | فروش و ثبت‌نام دوره | /courses/{id}/enrollments /course-orders /my-courses؛ course_enrollments, access_grants, order_items | رایگان بدون درگاه؛ پولی فقط با تأیید سروری؛ پرداخت موفق دقیقاً یک ثبت‌نام | B10,B11,B34 | P1·23 |
| B36 | آزمون دوره و گواهی | /course-exams /course-attempts/{id}/submit /my-certificates | سقف تلاش سمت سرور؛ ارسال دوباره گواهی تکراری نسازد؛ کد استعلام | B34,B35,B39 | P1·27 |
| B37 | تست روان‌شناسی و تفسیر | /psych-tests/{id}/attempts /psych-attempts/{id}/submit /me/psych-results | رضایت پیش از اجرا؛ نسخه پاسخ ثابت؛ تفسیر ردپذیر به مصوبه؛ نتیجه دیگران دیده نشود | B02,B04,B13,B41 | P1·37 |
| B38 | پیام، اعلان، SMS، ایمیل | /message-threads /messages /communication-preferences | فقط اعضای مجاز؛ داده درمانی در SMS/ایمیل ممنوع؛ شکست کانال قابل تلاش مجدد | B02,B04,B12,B39 | P0·26 |
| B39 | فایل امن | /files/upload-intents /files/{id}/complete /files/{id}/download-ticket | محدودیت حجم/نوع واقعی؛ اسکن+قرنطینه؛ مجوز در هر دانلود؛ لینک منقضی کار نکند | B02,B04 | P0·22 |
| B40 | نقشه و جست‌وجوی شعب | /public/branches /public/branches/nearby | فقط منتشرشده؛ ساعت واقعی روز؛ مکان کاربر فقط مرتب‌سازی و ذخیره نشود | B31,ADR-06 | P0·12 |
| B41 | رضایت و حاکمیت داده | /consents /consents/{id}/revoke /audit/access؛ consents, consent_versions, access_events | هیچ داده درمانی بدون رضایت معتبر؛ ابطال آینده را قطع و سابقه حفظ کند؛ متن نسخه تغییرناپذیر | B02,B04 | P0·16 |

## 18) فرایندهای BPMN — وضعیت
| # | نام | اقلام | وضعیت |
|---|---|---|---|
| 1 | رزرو نوبت و پرداخت | B09+B10+B11+B12 | نام معلوم؛ دیاگرام نیازمند سند کامل |
| 2 | خرید دوره، آزمون و گواهی | B34+B35+B36 | نام معلوم |
| 3 | پرونده دیجیتال و جلسه درمانی | B13+B14+B15+B41 | نام معلوم |
| 4 | تست روان‌شناسی و تفسیر | B37+B41 | نام معلوم |
| 5 | استرداد وجه | B20+B22 | نام معلوم؛ دیاگرام ناقص |
| 6 | ؟ | ؟ | دریافت نشده |
| 7 | ؟ | ؟ | دریافت نشده |

نکته اجرایی: پیاده‌سازی بر پایه State Machineها (بند 6) و قرارداد API (بند 7) جلو می‌رود؛ دیاگرام‌های BPMN سندِ مستندسازی هستند.

## 19) وضعیت پیاده‌سازی
- [x] گام 0: PowerShell 7.6.6 · Git 2.55 · اولین commit
- [x] گام 5: اسکلت Backend + B01 (این گام)
- [ ] گام 6: B02 — ورود OTP (S2) — نیازمند تصمیم D04 یا فرستنده mock
- [ ] ادامه طبق اسپرینت‌های S3–S16

## 20) سؤالات باز
1. BPMN 06/07 + بخش 08a — ارسال یا صرف‌نظر؟
2. نام پوشه محلی `rose-clinic` بماند؟ (داخل پروژه نام‌گذاری سند: roz)
3. D04 پیامک برای B02: کاوه‌نگار / فراز / ملی‌پیامک / فعلاً mock؟
4. D02 درگاه برای B10 (بعداً لازم می‌شود)

---

## 21) بروزرسانی v0.3.1 — استخراج کامل شد
- BPMN انتهای فرایند 05 + فرایند 06 (بارگذاری امن فایل / B39) + فرایند 07 (انتشار محتوا با بازبینی علمی / B33+B41) دریافت شد
- بخش 08 (صفحات و وایرفریم + الزامات UI) دریافت شد
- جزییات کامل در `docs/bpmn-and-ui.md` — لیست «دریافت‌نشده» در بند 0 این فایل منسوخ است
- ردیف‌های اصلاح‌شده جدول بند 18: فرایند 05 = کامل | فرایند 06 = بارگذاری امن فایل (B39) | فرایند 07 = انتشار محتوا با بازبینی علمی (B33+B41)

---

## 23) گام 7 — B03 + B04 پیاده‌سازی شد (اسپرینت S3)
- RBAC طبق سند §12: core.roles/permissions/role_permissions/user_roles + audit.audit_logs (مهاجرت 0003)
- 8 نقش سند seed شدند؛ مجوزهای اولیه: applicants.create/read، roles.read/assign
- require_permission: رد 403 + ثبت denied در audit (قاعده صریح B04: رد و ثبت، نه پنهان‌سازی)
- B03: POST/GET /applicants با تکراری‌یابی دولایه (applicant موجود → 409 با شناسه؛ شماره دارای حساب → 409 با user_id)
- B04: /roles، /users/{id}/roles (GET/POST/DELETE) + /me حالا نقش‌های واقعی برمی‌گرداند
- بوت‌استرپ: scripts/seed_roles.py (idempotent) + scripts/promote_admin.py برای اولین مدیر
- ماتریس دسترسی خودکار: 14 تست جدید (جمع 34) — الزام سند §12 (تست ماتریس در هر PR)
- تصمیم‌ها: صفحه‌بندی limit/offset سقف 100 (cursor بعداً)؛ برانچ‌اسکوپ ذخیره می‌شود و از S4 عملیاتی می‌شود؛ audit بدون FK به users (پایداری ممیزی)
- پیش‌فرض‌های عددی B02 بسته شد: همان مقادیر config (3/10min per phone، 20/10min per IP، نشست 7 روز) — قابل تغییر بدون کد
- D02 درگاه: باز — در S8 با آداپتور mock پیاده می‌شود تا با تصمیم آینده فقط یک کلاس عوض شود

---

## 24) گام 8 — B05 + B06 + B31 پیاده‌سازی شد (اسپرینت S4)
- مهاجرت 0004: specialties/services/consultants/credentials/verification_reviews/clinics/branches/branch_service_offerings — همگی در schema core (داده مرجع)؛ booking برای نوبت‌ها محفوظ است
- B05: eligibility = status approved + حداقل مدرک verified با expires_at معتبر؛ /consultants پیش‌فرض فقط قابل‌رزرو؛ /verification-reviews تأیید مدرک → ارتقای مشاور؛ لینک مشاور به کاربر → نقش consultant خودکار
- B06: مدت > 0 با CheckConstraint + Pydantic؛ خدمت غیرفعال از فهرست و خدمات شعبه حذف می‌شود
- B31: slug یکتا (clinic/branch/specialty)، lat/lon دو لایه (Pydantic + CheckConstraint)، شعبه draft/published/archived و فقط published عمومی؛ offerings: خدمت ناموجود یا غیرفعال در شعبه نمایش داده نمی‌شود
- برانچ‌اسکوپ عملیاتی شد: scoped_branch_ids در PATCH /branches/{id}؛ رد خارج‌از‌scope → 403 + audit
- مجوزهای جدید: services.manage، consultants.read/manage/review، clinics.manage، branches.manage (system_admin)
- حوادث محیطی: کانتینرها خاموش شده بودند (ConnectionTimeout) → با docker compose up ترمیم شد

---

## 25) گام 9 — B07 + B32 پیاده‌سازی شد (اسپرینت S5)
- مهاجرت 0005: core.tariffs + core.tariff_versions + core.topics
- B07: بازه نیمه‌باز [from, to)؛ هم‌پوشانی → 409 TARIFF_OVERLAP؛ مجاورت مجاز؛ نسخه باز با PATCH صریح بسته می‌شود (بستن دوباره → 409)؛ CheckConstraint بازه معتبر
- /pricing/quote?at=... : snapshot قیمت در زمان دلخواه — مبنای سفارش S8 («قیمت گذشته تغییر نکند»)؛ تعرفه شعبه‌specific مقدم بر سراسری؛ فاقد تعرفه → 404
- B32: درخت موضوع با جلوگیری چرخه (پیمایش اجداد) → 409 TOPIC_CYCLE؛ حذف فقط برگ بدون فرزند؛ غیرفعال‌سازی از public/topics حذف و سابقه حفظ می‌شود؛ /public/topics بدون احراز هویت
- مجوزهای جدید: tariffs.manage، topics.manage (system_admin)؛ رد دسترسی‌ها audit می‌شود
- محیط: compose با restart: unless-stopped به‌روز شد (ری‌استارت خودکار کانتینرها)
- content_topics به B33 موکول شد (نیازمند جدول contents)

---

## 26) گام 10 — B08 پیاده‌سازی شد (اسپرینت S6)
- مهاجرت 0006: booking.availability_weekly_rules + booking.availability_exceptions (اولین جداول schema booking)
- قواعد هفتگی به ساعت دیواری محلی (TZ سراسری Asia/Tehran در config) و ماده‌سازی به UTC هنگام تولید اسلات — سازگار با قاعده UTC سند
- استثنا = بازه بلاک UTC (پوشش مرخصی و بلاک موردی)؛ حذف کامل روز با یک استثنا شبانه‌روزی
- مولد اسلات به‌صورت تابع خالص services/slots.py با now تزریقی → 6 تست واحد قطعی (جاافتادن کامل در پنجره، تقسیم با استثنا، حذف گذشته، مرخصی کل روز، روز اشتباه هفته)
- API: PUT/GET rules (جایگزینی کامل + رد هم‌پوشانی 409) · POST/DELETE exceptions · GET availability (اسلات آزاد per خدمت، سقف 31 روز)
- مالکیت تقویم: مشاور فقط خودش، system_admin همه؛ رد → 403 + audit
- سرویس غیرفعال → 404 برای query اسلات؛ کسر نوبت‌های رزروشده در B09/S7 به همان تابع خالص اضافه می‌شود
- محیط: scripts/env-check.ps1 ساخته شد (Docker check + compose up + pytest) — همیشه قبل از کار اجرا شود

---

## 27) گام 11 — B09 پیاده‌سازی شد (اسپرینت S7)
- مهاجرت 0007: booking.slot_claims + booking.appointments + CREATE EXTENSION btree_gist + دو Exclusion Constraint (منع تعارض در سطح DB — «دو رزرو ناسازگار قطعی نشوند»)
- Hold با TTL=10min (قابل تنظیم)، snapshot قیمت لحظه hold، مصرف یک‌بار، انقضای lazy (expired → آزاد)
- نوبت از hold: بدون قیمت/صفر → confirmed (نوبت قطعی رایگان طبق BPMN فرایند 01)؛ با قیمت → pending_payment
- اعتبارسنجی سه‌لایه: پنجره تقویم (rules−exceptions) → تداخل با hold/نوبت فعال → Exclusion Constraint به‌عنوان حصار نهایی
- لغو فقط از pending_payment/confirmed؛ وضعیت‌های State Machine سند
- endpoint اسلات حالا نوبت‌ها و holdهای فعال را هم از دسترس‌پذیری کم می‌کند
- ترمیم‌ها: compose بازنویسی تمیز، دو باگ تست s5، slots.py تمیز، scripts/db_sync.py برای هم‌ترازی alembic/create_all
- D02 درگاه هنوز باز: در S8 آداپتور mock ساخته می‌شود

---

## 28) گام 12 — B10 + B11 پیاده‌سازی شد (اسپرینت S8)
- مهاجرت 0008: finance.orders/payments/invoices/invoice_items + سکانس شماره فاکتور
- B10: POST /orders با Idempotency-Key الزامی (تکرار همان کلید → همان سفارش، 200 + meta.idempotent_replay)؛ سفارش فقط از نوبت pending_payment با snapshot؛ سفارش فعال تکراری → 409
- payments/start: آداپتور درگاه (MockGateway طبق D02 باز)؛ پرداخت فعال موازی → 409
- payments/callback: بدون احراز هویت کاربر؛ allowlist IP قابل تنظیم (خالی=فقط dev)؛ تأیید با adapter سمت سرور؛ callback تکراری no-op (200 + noop) — قاعده صریح سند؛ success → order=paid + نوبت=confirmed + صدور فاکتور در همان تراکنش؛ failure → order=failed و امکان سفارش جدید
- B11: فاکتور خودکار per paid order (idempotent)؛ شماره یکتا INV-{سال}-{سکانس}؛ مبلغ = snapshot سفارش؛ GET /invoices/{id} برای مالک یا نقش مالی؛ GET /invoices/{id}.pdf با PDF حداقلی بدون وابستگی (PDF فارسی به فاز UI موکول — تصمیم ثبت‌شده)
- مجوزهای جدید: orders.read، invoices.read → finance + system_admin
- ترمیم‌های این مرحله: باگ db_sync (heads)، B904، بازنویسی idempotent فایل‌های گام 11 (booking/availability/main/conftest انعطاف‌پذیر)

---

## 29) گام 12 — B10 + B11 پیاده‌سازی شد (اسپرینت S8)
- مهاجرت 0008: finance.orders/payments/invoices/invoice_items + سکانس شماره فاکتور (خودترمیم در سرویس فاکتور نیز)
- B10: POST /orders با Idempotency-Key الزامی (تکرار کلید → همان سفارش، 200 + meta.idempotent_replay)؛ سفارش فقط از نوبت pending_payment با snapshot؛ سفارش فعال تکراری → 409
- payments/start: آداپتور درگاه (MockGateway طبق D02 باز)؛ پرداخت فعال موازی → 409
- payments/callback: بدون احراز کاربر؛ allowlist IP (خالی=فقط dev)؛ تأیید سروری با adapter؛ callback تکراری no-op (قاعده صریح سند)؛ success → paid + confirmed + فاکتور در همان تراکنش؛ failure → failed و امکان سفارش جدید
- B11: فاکتور خودکار per paid order (idempotent)؛ شماره یکتا INV-{سال}-{سکانس}؛ مبلغ = snapshot سفارش؛ دسترسی مالک یا مالی؛ PDF حداقلی بدون وابستگی (PDF فارسی به فاز UI موکول)
- مجوزهای جدید: orders.read، invoices.read → finance + system_admin
- ترمیم‌های همراه: E501 booking.py، سکانس در conftest، invoicing بازنویسی تمیز
