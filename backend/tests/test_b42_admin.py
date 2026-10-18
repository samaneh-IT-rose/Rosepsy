"""B42 — Admin panel API (سند ساختاریافته شناسایی صفحات).

Covers the endpoints backing the documented pages:
- dashboard / provinces / cities (doc s.3, s.4.1, s.9)
- users: list + regional filters + columns + row-drop + edit + switch-session (s.4)
- profile & services + «بیشتر» event-details (s.5)
- centers: list/filters/export/create/groups (s.6)
- reports: landing (10 cards), events, consultants, invited, reservation-requests (s.7, s.8)
- logs (s.3.1.2 item ۲۷)
- RBAC: admin.panel required; 403 without permission; 401 without token (s.11 item ۱۵)
"""
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import text

from tests.helpers import SessionLocal, client, grant, h, login

PHONE = iter(range(9142100000, 9142199999))
TZ = ZoneInfo("Asia/Tehran")


def _phone() -> str:
    return "0" + str(next(PHONE))


def _system_headers() -> dict:
    token, _uid = grant(_phone(), "system_admin")
    return h(token)


def _admin_headers() -> dict:
    token, _uid = grant(_phone(), "national_admin")
    return h(token)


# ─────────────── reference data & dashboard (s.3 / s.9) ───────────────


def test_dashboard_shape_and_menu_count():
    r = client.get("/api/v1/admin/dashboard", headers=_admin_headers())
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # doc s.3.1.2: 29 menu items; s.3.1.1: 5 desktop shortcuts; s.3.2: user section
    assert len(data["menus"]) == 29
    assert len(data["shortcuts"]) == 5
    assert data["identity"]["badge"] == "کشور"
    assert len(data["user_section"]["links"]) == 5
    # legacy spelling preserved (doc note under s.3.1.2)
    assert any(m["path"] == "/sms-managment" for m in data["menus"])
    assert {"users", "centers", "consultants", "referrals"} <= set(data["stats"].keys())


def test_provinces_list_includes_all_31_plus_kol_keshvar():
    r = client.get("/api/v1/admin/provinces", headers=_admin_headers())
    assert r.status_code == 200
    codes = {p["code"] for p in r.json()["data"]}
    assert codes == set(range(0, 32))  # doc s.9: 0=کل کشور + 31 استان
    names = {p["name"] for p in r.json()["data"]}
    assert "کل کشور" in names and "یزد" in names


def test_cities_require_valid_province():
    hok = _admin_headers()
    r = client.get("/api/v1/admin/cities?province_code=0", headers=hok)
    assert r.status_code == 422  # «کل کشور» is filter-only, never a city source
    r = client.get("/api/v1/admin/cities?province_code=32", headers=hok)
    assert r.status_code == 422


# ─────────────── users management (s.4) ───────────────


def test_users_list_columns_and_paging_rules():
    hok = _admin_headers()
    r = client.get("/api/v1/admin/users?length=10", headers=hok)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["columns"] == [
        "کد", "نام کاربری", "نام و نام خانوادگی", "نام پدر", "جنسیت",
        "شماره همراه", "استان", "تحصیلات", "تاریخ تولد", "تاریخ ثبت‌نام", "آخرین ورود",
    ]
    # DataTables-style lengths (s.4.5): 10/25/50/100/همه
    for n in (25, 50, 100, -1):
        assert client.get(f"/api/v1/admin/users?length={n}", headers=hok).status_code == 200
    assert client.get("/api/v1/admin/users?length=7", headers=hok).status_code == 422


def test_users_regional_filter_province_zero_means_all():
    hok = _admin_headers()
    # province=0 («کل کشور») must not filter anything
    r_all = client.get("/api/v1/admin/users?length=-1&province=0", headers=hok)
    r_none = client.get("/api/v1/admin/users?length=-1", headers=hok)
    assert r_all.status_code == r_none.status_code == 200
    assert (
        r_all.json()["data"]["records_filtered"]
        == r_none.json()["data"]["records_filtered"]
    )


def test_user_row_drop_details_and_last_login():
    ph = _phone()
    login(ph)  # a fresh user gets a row + last_login_at set
    hok = _admin_headers()
    r = client.get("/api/v1/admin/users?length=-1", headers=hok)
    row = next(
        x for x in r.json()["data"]["rows"] if x["mobile"].endswith(ph[-10:])
    )
    assert set(row["details"].keys()) == {
        "username", "email", "address", "postal_code", "registration_source",
    }
    # «آخرین ورود» recorded on OTP login (doc s.4.2)
    assert row["last_login_at"] is not None


def test_edit_user_updates_profile_and_audits():
    hok = _admin_headers()
    token, uid = login(_phone())
    r = client.patch(
        f"/api/v1/admin/users/{uid}",
        json={"first_name": "زلیخا", "last_name": "برهانی", "email": "z@example.com"},
        headers=hok,
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["changed"]) == {"first_name", "last_name", "email"}
    r = client.get(f"/api/v1/admin/users/{uid}", headers=hok)
    assert r.json()["data"]["personal"]["email"] == "z@example.com"


def test_edit_user_validation_rules():
    hok = _admin_headers()
    _, uid = login(_phone())
    bad_national_id = client.patch(
        f"/api/v1/admin/users/{uid}", json={"national_id": "123"}, headers=hok
    )
    assert bad_national_id.status_code == 422
    bad_gender = client.patch(
        f"/api/v1/admin/users/{uid}", json={"gender": "other"}, headers=hok
    )
    assert bad_gender.status_code == 422
    missing = client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}", json={"email": "x@y.z"}, headers=hok
    )
    assert missing.status_code == 404


def test_switch_session_creates_session_and_audit():
    hok = _admin_headers()
    target_token, target_uid = login(_phone())
    r = client.post(f"/api/v1/admin/users/{target_uid}/switch-session", headers=hok)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    # the issued token must actually authenticate the target user
    r2 = client.get("/api/v1/me", headers=h(data["access_token"]))
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == target_uid
    # mandatory audit (doc s.11 item ۱۵)
    with SessionLocal() as db:
        n = db.execute(
            text(
                "SELECT count(*) FROM audit.audit_logs "
                "WHERE action='users.switch_session' AND resource_id::text = :u"
            ),
            {"u": target_uid},
        ).scalar_one()
    assert n >= 1


def test_switch_session_on_missing_user_404():
    r = client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/switch-session", headers=_admin_headers()
    )
    assert r.status_code == 404


# ─────────────── profile & services (s.5) ───────────────


def _fixture_ids() -> tuple[str, str, str]:
    """(service_id, consultant_id, branch_id) created via real APIs."""
    sys_h = _system_headers()
    sid = client.post(
        "/api/v1/services",
        json={"name": "خدمت ادمین", "duration_minutes": 45},
        headers=sys_h,
    ).json()["data"]["id"]
    cid = client.post(
        "/api/v1/consultants", json={"display_name": "مشاور ادمین"}, headers=sys_h
    ).json()["data"]["id"]
    admin_h = _admin_headers()
    bid = client.post(
        "/api/v1/admin/centers",
        json={"name": "کلینیک جلسات ادمین", "province_code": 8, "city": "تهران"},
        headers=admin_h,
    ).json()["data"]["id"]
    return sid, cid, bid


def _seed_session_for(uid: str) -> None:
    sid, cid, bid = _fixture_ids()
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO core.referrals (id, code, user_id, contract_title,"
                " user_tariff, status, source, branch_id, consultant_id)"
                " VALUES (:id, nextval('core.referrals_code_seq')::bigint, :uid,"
                " 'مددجو', 0, 'under_review', 'سها', :bid, :cid)"
            ),
            {"id": str(uuid.uuid4()), "uid": uid, "bid": bid, "cid": cid},
        )
        db.execute(
            text(
                "INSERT INTO booking.appointments (id, user_id, service_id,"
                " branch_id, consultant_id, start_at, end_at, status,"
                " price_snapshot, code, referral_id, acute_status)"
                " VALUES (:id, :uid, :sid, :bid, :cid,"
                " now() - interval '1 day', now() - interval '30 minutes',"
                " 'completed', '{\"amount\": 0}',"
                " nextval('booking.appointments_code_seq'),"
                " (SELECT id FROM core.referrals WHERE user_id = :uid LIMIT 1), 'no')"
            ),
            {"id": str(uuid.uuid4()), "uid": uid, "sid": sid, "bid": bid, "cid": cid},
        )
        db.commit()


def test_profile_services_columns_and_event_details():
    hok = _admin_headers()
    token, uid = login(_phone())
    _seed_session_for(uid)
    r = client.get(f"/api/v1/admin/users/{uid}", headers=hok)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["services"]["columns"] == [
        "شناسه", "شناسه ارجاع", "سرویس", "قرارداد", "تعرفه کاربر", "کیس حاد",
        "مشاور", "مرکز", "وضعیت", "تاریخ شروع", "تاریخ پایان", "بیشتر",
    ]
    assert len(data["services"]["rows"]) == 1
    row = data["services"]["rows"][0]
    assert row["contract"] == "مددجو"
    assert row["user_tariff"] == 0
    assert row["details_options"] == [
        {"value": "0", "title": "جزئیات"},
        {"value": "EVENT", "title": "جزئیات جلسه"},
        {"value": "REFF", "title": "جزئیات ارجاع"},
    ]
    # «بیشتر» → event details (doc s.5.5)
    code = row["code"]
    ev = client.get(f"/api/v1/admin/event-details/{code}?kind=EVENT", headers=hok)
    assert ev.status_code == 200 and ev.json()["data"]["event"]["code"] == code
    rf = client.get(f"/api/v1/admin/event-details/{code}?kind=REFF", headers=hok)
    assert rf.status_code == 200
    assert rf.json()["data"]["referral"]["contract"] == "مددجو"
    bad = client.get(f"/api/v1/admin/event-details/{code}?kind=WRONG", headers=hok)
    assert bad.status_code == 422


def test_referral_code_sequence_exceeds_int4():
    """Doc sample 100136613430 > 2^31-1 — the BigInteger regression guard."""
    hok = _admin_headers()
    _, uid = login(_phone())
    _seed_session_for(uid)
    with SessionLocal() as db:
        code = db.execute(
            text("SELECT max(code) FROM core.referrals WHERE user_id = :u"), {"u": uid}
        ).scalar_one()
    assert code > 2**31 - 1
    # and the API returns it without overflow errors
    r = client.get(f"/api/v1/admin/users/{uid}", headers=hok)
    assert r.json()["data"]["services"]["rows"][0]["referral_code"] == code


def test_profile_read_writes_access_event():
    hok = _admin_headers()
    _, uid = login(_phone())
    client.get(f"/api/v1/admin/users/{uid}", headers=hok)
    with SessionLocal() as db:
        n = db.execute(
            text(
                "SELECT count(*) FROM audit.access_events "
                "WHERE action='admin.profile.read' AND subject_user_id = :u"
            ),
            {"u": uid},
        ).scalar_one()
    assert n >= 1  # هر خواندن پرونده = access_event (B13)


# ─────────────── centers (s.6) ───────────────


def test_centers_filters_activation_semantics():
    hok = _admin_headers()
    # seed three centers: two active, one inactive
    ok = client.post(
        "/api/v1/admin/centers",
        json={"name": "کلینیک تست فعال", "province_code": 8, "city": "تهران"},
        headers=hok,
    )
    assert ok.status_code == 201, ok.text
    center_id = ok.json()["data"]["id"]
    deact = client.patch(
        f"/api/v1/admin/centers/{center_id}", json={"is_active": False}, headers=hok
    )
    assert deact.status_code == 200 and deact.json()["data"]["is_active"] is False
    client.post(
        "/api/v1/admin/centers",
        json={"name": "کلینیک تست دوم", "province_code": 8, "city": "تهران"},
        headers=hok,
    )
    active = client.get("/api/v1/admin/centers?activation=1&length=-1", headers=hok)
    inactive = client.get("/api/v1/admin/centers?activation=0&length=-1", headers=hok)
    allc = client.get("/api/v1/admin/centers?activation=all&length=-1", headers=hok)
    # «همه» = همه رکوردها (doc s.11 item ۵: مقدار فنی گزینه «همه» resolved to 'all')
    assert (
        inactive.json()["data"]["records_filtered"]
        + active.json()["data"]["records_filtered"]
        == allc.json()["data"]["records_filtered"]
    )
    assert any(
        c["name"] == "کلینیک تست فعال" and not c["is_active"]
        for c in inactive.json()["data"]["rows"]
    )


def test_centers_export_covers_all_filtered_rows_with_bom():
    hok = _admin_headers()
    r = client.get("/api/v1/admin/centers/export?activation=1", headers=hok)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.content.decode("utf-8-sig")
    lines = body.strip().splitlines()
    assert lines[0] == "نام کلینیک,استان,شهر,وضعیت کلینیک,شناسه"
    # export must cover the same filtered set (doc s.11: scope resolved)
    listing = client.get(
        "/api/v1/admin/centers?activation=1&length=-1", headers=hok
    ).json()["data"]
    assert len(lines) - 1 == listing["records_filtered"]


def test_center_groups_create_and_duplicate_guard():
    hok = _admin_headers()
    r = client.post(
        "/api/v1/admin/center-groups", json={"name": "گروه تستیک"}, headers=hok
    )
    assert r.status_code == 201
    dup = client.post(
        "/api/v1/admin/center-groups", json={"name": "گروه تستیک"}, headers=hok
    )
    assert dup.status_code == 409
    lst = client.get("/api/v1/admin/center-groups", headers=hok)
    assert any(g["name"] == "گروه تستیک" for g in lst.json()["data"])


# ─────────────── reports (s.7 / s.8) ───────────────


def test_reports_landing_has_three_groups_ten_cards():
    r = client.get("/api/v1/admin/reports", headers=_admin_headers())
    assert r.status_code == 200
    groups = r.json()["data"]["groups"]
    assert len(groups) == 3
    assert sum(len(g["cards"]) for g in groups) == 10  # 4 + 3 + 3
    paths = [c["path"] for g in groups for c in g["cards"]]
    assert "/event-report" in paths and "/admin-referrs-requests" in paths


def _seed_two_sessions(uid: str) -> None:
    sid, cid, bid = _fixture_ids()
    with SessionLocal() as db:
        for i, status in enumerate(("completed", "confirmed")):
            db.execute(
                text(
                    "INSERT INTO booking.appointments (id, user_id, service_id,"
                    " branch_id, consultant_id, start_at, end_at, status,"
                    " price_snapshot, code)"
                    " VALUES (:id, :uid, :sid, :bid, :cid,"
                    f" now() - interval '{i} days', now(), '{status}',"
                    " '{\"amount\": 150000}',"
                    " nextval('booking.appointments_code_seq'))"
                ),
                {"id": str(uuid.uuid4()), "uid": uid, "sid": sid, "bid": bid, "cid": cid},
            )
        db.commit()


def test_event_reports_split_done_vs_undone():
    hok = _admin_headers()
    _, uid = login(_phone())
    _seed_two_sessions(uid)
    done = client.get(
        "/api/v1/admin/reports/events?kind=individual&state=done&length=-1", headers=hok
    ).json()["data"]
    undone = client.get(
        "/api/v1/admin/reports/events?kind=individual&state=undone&length=-1", headers=hok
    ).json()["data"]
    assert done["total"] >= 1 and undone["total"] >= 1
    # same session cannot appear in both reports
    done_codes = {r["code"] for r in done["rows"]}
    undone_codes = {r["code"] for r in undone["rows"]}
    assert not (done_codes & undone_codes)


def test_consultant_report_groupings_and_csv():
    hok = _admin_headers()
    _, uid = login(_phone())
    _seed_two_sessions(uid)
    r = client.get("/api/v1/admin/reports/consultants?group_by=service", headers=hok)
    assert r.status_code == 200
    rows = r.json()["data"]["rows"]
    assert rows and all("services" in row for row in rows)
    totals = {row["name"]: row["total_count"] for row in rows}
    assert sum(totals.values()) >= 2
    csv = client.get("/api/v1/admin/reports/consultants?format=csv", headers=hok)
    assert csv.status_code == 200 and "ردیف,نام,کد ملی" in csv.content.decode("utf-8-sig")


def test_invited_and_reservation_request_reports():
    hok = _admin_headers()
    ph = _phone()
    token, uid = login(ph)
    client.patch(
        f"/api/v1/admin/users/{uid}",
        json={"registration_source": "توسط سها"},
        headers=hok,
    )
    invited = client.get("/api/v1/admin/reports/invited?length=-1", headers=hok)
    assert invited.status_code == 200
    assert any(
        row["mobile"].endswith(ph[-10:]) for row in invited.json()["data"]["rows"]
    )
    _seed_two_sessions(uid)
    reqs = client.get(
        "/api/v1/admin/reports/reservation-requests?length=-1", headers=hok
    )
    assert reqs.status_code == 200
    assert reqs.json()["data"]["total"] >= 1  # confirmed session counts


# ─────────────── logs (s.3.1.2 item ۲۷) ───────────────


def test_logs_list_and_search():
    ph_admin = _phone()
    token, admin_uid = grant(ph_admin, "national_admin")
    hok = h(token)
    ph = _phone()
    token2, uid = login(ph)
    # PATCH profile writes an audit entry (users.manage:edit) — read-only listing
    # does not audit by design. The audit ACTOR is the admin performing the edit.
    client.patch(f"/api/v1/admin/users/{uid}", json={"email": "log@example.com"}, headers=hok)
    r = client.get("/api/v1/admin/logs?length=5", headers=hok)
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= 1
    r2 = client.get("/api/v1/admin/logs?q=" + ph_admin[-10:], headers=hok)
    assert r2.status_code == 200
    assert r2.json()["data"]["total"] >= 1  # search by actor phone


# ─────────────── RBAC (s.11 item ۱۵) ───────────────


def test_admin_endpoints_require_permission():
    token, _uid = login(_phone())  # plain user, no roles
    for path in (
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users?length=10",
        "/api/v1/admin/centers?length=10",
        "/api/v1/admin/reports",
        "/api/v1/admin/logs?length=5",
    ):
        r = client.get(path, headers=h(token))
        assert r.status_code == 403, f"{path} -> {r.status_code}"


def test_admin_endpoints_require_token():
    for path in (
        "/api/v1/admin/dashboard",
        "/api/v1/admin/provinces",
        "/api/v1/admin/reports",
    ):
        r = client.get(path)
        assert r.status_code == 401, f"{path} -> {r.status_code}"


def test_reports_read_permission_denied_for_auditor_dpo():
    token, _uid = grant(_phone(), "auditor_dpo")  # has audit.access.read only
    r = client.get("/api/v1/admin/reports", headers=h(token))
    assert r.status_code == 403
