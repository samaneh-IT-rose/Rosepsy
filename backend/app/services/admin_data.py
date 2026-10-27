"""Single source of truth for the admin panel structure (B42).

Every item below is transcribed from «سند ساختاریافته شناسایی صفحات، فیلدها و
ستون‌های سامانه — مجموعه راه زندگی رز سفید» (sections ۳.۱، ۳.۲ و ۷).

Path spellings are preserved exactly as the document requires, including the
legacy «sms-managment» spelling (doc note under s.3.1.2).
"""

DASHBOARD_IDENTITY = {
    "title": "مدیر عامل مجموعه راه زندگی رز سفید ـ ادمین ملی",
    "badge": "کشور",
    "theme": "anthracite-gradient",
}

# doc s.3.1.1 — desktop-only shortcuts (hidden on mobile, per document).
SHORTCUTS = [
    {"title": "تنظیمات", "path": "/system-settings",
        "icon": "icon-gear"},
    {"title": "کاربران", "path": "/admin-editusers",
        "icon": "icon-users"},
    {"title": "مراکز و کلینیک‌ها", "path": "/centers",
        "icon": "icon-globe"},
    {"title": "گزارش فعالیت کاربران", "path": "/logs",
        "icon": "icon-target"},
    {"title": "گزارشات", "path": "/reports",
        "icon": "icon-pie-chart"},
]

# doc s.3.1.2 — full national-admin menu (29 items).
MENUS = [
    {"title": "تنظیمات", "path": "/system-settings",
        "icon": "dashboardlist-gear-2"},
    {"title": "مدیریت سهمیه", "path": "/define-budget",
        "icon": "dashboardlist-management-setting"},
    {"title": "کاربران", "path": "/admin-editusers",
        "icon": "dashboardlist-group"},
    {"title": "مراکز و کلینیک‌ها", "path": "/centers",
        "icon": "folder-net"},
    {"title": "نقش‌ها و قراردادها", "path": "/admin-roles",
        "icon": "folder-docs"},
    {"title": "ثبت گروهی قرارداد", "path": "/admin-add-multi-contract",
        "icon": "folder-pen"},
    {"title": "ارجاعات سها", "path": "/API-referrs",
        "icon": "folder-open"},
    {"title": "استعلام وضعیت مددجو", "path": "/inquiry-person-status",
        "icon": "dashboardlist-user-review"},
    {"title": "بررسی مشاوره‌ها", "path": "/consultations-confirm",
        "icon": "folder-close"},
    {"title": "بررسی جلسات گروهی", "path": "/group-consultations-confirm",
        "icon": "folder-close"},
    {"title": "کاربران معرفی‌شده", "path": "/invitepersons",
        "icon": "folder-favs"},
    {"title": "درخواست‌های رزرو کاربران", "path": "/referrs-requests",
        "icon": "file-js"},
    {"title": "موارد حاد", "path": "/checkEMS",
        "icon": "dashboardlist-emergency"},
    {"title": "پرونده کاربر", "path": "/profile",
        "icon": "dashboardlist-user-review"},
    {"title": "عملکرد مالی", "path": "/payments",
        "icon": "dashboardlist-daily-report"},
    {"title": "گزارش به تفکیک خدمت‌گیرنده", "path": "/report-recipient",
        "icon": "dashboardlist-recipient-report"},
    {"title": "مدیریت مالیات مشاوران", "path": "/admin-consultant-tax",
        "icon": "dashboardlist-consultant-tax"},
    {"title": "کیف پول‌ها", "path": "/wallets",
        "icon": "dashboardlist-wallet"},
    {"title": "کدهای تخفیف", "path": "/discounts",
        "icon": "dashboardlist-discount"},
    {"title": "استرداد وجه", "path": "/refunds",
        "icon": "dashboardlist-refund"},
    {"title": "حسابداری و تسویه", "path": "/accounting",
        "icon": "dashboardlist-accounting"},
    {"title": "آزمون‌های روان‌شناسی", "path": "/psych-tests",
        "icon": "dashboardlist-psych"},
    {"title": "مدیریت محتوا", "path": "/contents",
        "icon": "dashboardlist-contents"},
    {"title": "دوره‌های آموزشی", "path": "/courses",
        "icon": "dashboardlist-courses"},
    {"title": "گزارشات", "path": "/reports",
        "icon": "dashboardlist-report"},
    {"title": "BI", "path": "/bi",
        "icon": "dashboardlist-report"},
    {"title": "BI سهمیه‌ها", "path": "/bi-budget",
        "icon": "dashboardlist-pie-chart"},
    {"title": "BI موارد حاد", "path": "/bi-critical-cases",
        "icon": "dashboardlist-bi-critical-cases"},
    {"title": "BI نظارت حرفه‌ای", "path": "/professional-supervision-bi",
        "icon": "dashboardlist-report"},
    {"title": "پیامک‌ها", "path": "/sms-managment",
        "icon": "dashboardlist-notification"},
    {"title": "ارسال پیامک گروهی", "path": "/bulk-sms",
        "icon": "dashboardlist-notification"},
    {"title": "مدیریت پیام‌ها", "path": "/admin-messages",
        "icon": "dashboardlist-admin-messages"},
    {"title": "مدیریت مناسبت‌ها", "path": "/admin-special-occasions",
        "icon": "dashboardlist-special-occasions"},
    {"title": "گزارش فعالیت کاربران", "path": "/logs",
        "icon": "file-log"},
    {"title": "پشتیبانی ـ تیکت", "path": "/user-ticket",
        "icon": "file-chm"},
    {"title": "مدیریت راهنما", "path": "/admin-helps",
        "icon": "dashboardlist-help"},
]

# doc s.3.2 — user section (silver-gradient).
USER_SECTION = {
    "title": "بخش کاربری",
    "badge": "کاربر",
    "theme": "silver-gradient",
    "links": [
        {"title": "رزرو مشاوره", "path": "/eventReserve",
        "icon": "dashboardlist-technical-support"},
        {"title": "سامانه آموزشی", "path": "https://roseacademy.ir",
        "icon": "dashboardlist-motafaregh"},
        {"title": "سایت راه زندگی", "path": "https://rosecenter.ir",
        "icon": "dashboardlist-logo"},
        # doc: «در متن، آدرس واقعی مشخص نشده و مقدار لینک # است» — preserved.
        {"title": "شبکه اجتماعی اینستاگرام", "path": "#",
        "icon": "dashboardlist-instagram"},
        {"title": "شبکه اجتماعی بله", "path": "https://ble.ir/amoozesh_rahezendegiros2",
        "icon": "dashboardlist-bale"},
    ],
}

# doc s.7.2–7.4 — reports page: 3 groups, 10 cards (titles/descriptions/paths/
# icons/gradients verbatim).
REPORT_GROUPS = [
    {
        "title": "گزارشات جلسات مشاوره",
        "description": "مشاهده و بررسی جلسات فردی و گروهی",
        "icon": "icon-calendar",
        "gradient": "linear-gradient(135deg, #4e73df, #224abe)",
        "cards": [
            {
                "title": "جلسات مشاوره",
                "description": "گزارش کامل جلسات انجام‌شده",
                "path": "/event-report",
                "icon": "icon-clock",
                "gradient": "green-gradient",
            },
            {
                "title": "جلسات ناتمام",
                "description": "مشاوره‌هایی که هنوز تکمیل نشده‌اند",
                "path": "/undone-event-report",
                "icon": "icon-hourglass",
                "gradient": "red-gradient",
            },
            {
                "title": "جلسات گروهی",
                "description": "گزارش مشاوره‌های گروهی انجام‌شده",
                "path": "/event-group-report",
                "icon": "icon-users",
                "gradient": "green-gradient",
            },
            {
                "title": "جلسات گروهی ناتمام",
                "description": "مشاوره‌های گروهی تکمیل‌نشده",
                "path": "/undone-event-group-report",
                "icon": "icon-hourglass",
                "gradient": "red-gradient",
            },
        ],
    },
    {
        "title": "کاربران و درخواست‌ها",
        "description": "مدیریت کاربران، معرفی‌شده‌ها و درخواست‌های رزرو",
        "icon": "icon-user",
        "gradient": "linear-gradient(135deg, #1cc88a, #13855c)",
        "cards": [
            {
                "title": "مدیریت کاربران",
                "description": "مشاهده و ویرایش اطلاعات کاربران",
                "path": "/admin-editusers",
                "icon": "icon-users",
                "gradient": "blue-gradient",
            },
            {
                "title": "کاربران معرفی‌شده",
                "description": "فهرست افراد معرفی‌شده به سامانه",
                "path": "/invitepersons",
                "icon": "icon-star",
                "gradient": "orange-gradient",
            },
            {
                "title": "درخواست‌های رزرو",
                "description": "بررسی درخواست‌های رزرو کاربران",
                "path": "/admin-referrs-requests",
                "icon": "icon-paperclip",
                "gradient": "blue-gradient",
            },
        ],
    },
    {
        "title": "مدیریت و تنظیمات",
        "description": "کلینیک‌ها، تعرفه‌ها، پیامک‌ها و سایر تنظیمات",
        "icon": "icon-gear",
        "gradient": "linear-gradient(135deg, #f6c23e, #dda20a)",
        "cards": [
            {
                "title": "تعرفه‌ها و قراردادها",
                "description": "مدیریت تعرفه‌ها و تنظیمات قراردادها",
                "path": "/system-settings",
                "icon": "icon-gear",
                "gradient": "orange-gradient",
            },
            {
                "title": "مراکز و کلینیک‌ها",
                "description": "مشاهده و مدیریت مراکز مشاوره",
                "path": "/centers",
                "icon": "icon-globe",
                "gradient": "blue-gradient",
            },
            {
                "title": "مدیریت پیامک‌ها",
                "description": "ارسال و بررسی پیامک‌های سامانه",
                "path": "/sms-managment",
                "icon": "icon-speech",
                "gradient": "orange-gradient",
            },
        ],
    },
]

# doc s.9 — province reference data (code 0 «کل کشور» is the filter-only value).
PROVINCES: list[tuple[int, str]] = [
    (0, "کل کشور"),
    (1, "آذربایجان شرقی"),
    (2, "آذربایجان غربی"),
    (3, "اردبیل"),
    (4, "اصفهان"),
    (5, "البرز"),
    (6, "ایلام"),
    (7, "بوشهر"),
    (8, "تهران"),
    (9, "چهارمحال و بختیاری"),
    (10, "خراسان جنوبی"),
    (11, "خراسان رضوی"),
    (12, "خراسان شمالی"),
    (13, "خوزستان"),
    (14, "زنجان"),
    (15, "سمنان"),
    (16, "سیستان و بلوچستان"),
    (17, "فارس"),
    (18, "قزوین"),
    (19, "قم"),
    (20, "کردستان"),
    (21, "کرمان"),
    (22, "کرمانشاه"),
    (23, "کهگیلویه و بویراحمد"),
    (24, "گلستان"),
    (25, "لرستان"),
    (26, "گیلان"),
    (27, "مازندران"),
    (28, "مرکزی"),
    (29, "هرمزگان"),
    (30, "همدان"),
    (31, "یزد"),
]

# Display vocabularies (resolve doc s.11 ambiguities ۹ و ۱۰ with explicit maps).
APPOINTMENT_STATUS_FA = {
    "pending_payment": "در انتظار پرداخت",
    "confirmed": "تأییدشده",
    "in_progress": "در جریان",
    "completed": "انجام‌شده",
    "cancelled": "لغوشده",
    "no_show": "عدم حضور",
}

REFERRAL_STATUS_FA = {
    "under_review": "در حال بررسی",
    "approved": "تأییدشده",
    "rejected": "ردشده",
    "completed": "تکمیل‌شده",
}

ACUTE_STATUS_FA = {
    "no": "خیر",
    "pending": "در انتظار",
    "yes": "بله",
}

# EventDetails select (doc s.5.5) — options of the «بیشتر» control.
EVENT_DETAILS_OPTIONS = [
    {"value": "0", "title": "جزئیات"},
    {"value": "EVENT", "title": "جزئیات جلسه"},
    {"value": "REFF", "title": "جزئیات ارجاع"},
]

# Education options seen in the system samples (doc s.4.6 «بی‌سواد», s.5.2 «ابتدایی»).
EDUCATION_OPTIONS = [
    "بی‌سواد",
    "ابتدایی",
    "راهنمایی",
    "متوسطه",
    "دیپلم",
    "فوق دیپلم",
    "کارشناسی",
    "کارشناسی ارشد",
    "دکتری",
    "حوزه",
]
