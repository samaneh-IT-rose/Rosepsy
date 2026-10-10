from datetime import time

import pytest

from app.services.geo import haversine_km, is_open_now
from tests.helpers import client, grant, h

PHONE = iter(range(9141210000, 9141219999))


def _phone() -> str:
    return "0" + str(next(PHONE))


def _branch(hok, slug, lat, lon, city="تهران", status=None, hours=None):
    clinic_id = client.post(
        "/api/v1/clinics", json={"name": f"کلینیک {slug}", "slug": slug},
        headers=hok,
    ).json()["data"]["id"]
    bid = client.post(
        f"/api/v1/clinics/{clinic_id}/branches",
        json={
            "name": f"شعبه {slug}", "slug": f"{slug}-b", "city": city,
            "lat": lat, "lon": lon, "working_hours": hours,
        },
        headers=hok,
    ).json()["data"]["id"]
    if status:
        client.patch(f"/api/v1/branches/{bid}", json={"status": status}, headers=hok)
    return bid


def test_nearby_sorts_by_distance_and_excludes_drafts():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    # ونک نزدیک‌تر از مبدأ تست؛ میرداماد دورتر؛ شعبه پیش‌نویس غایب
    _branch(hok, "near-a", 35.7580, 51.4100, status="published")   # ~1.2km
    _branch(hok, "far-b", 35.7000, 51.3000, status="published")    # ~13km
    _branch(hok, "draft-c", 35.7600, 51.4200)                      # draft
    resp = client.get("/api/v1/public/branches/nearby", params={"lat": 35.7550, "lon": 51.4050})
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [b["name"] for b in data]
    assert len(data) == 2  # draft excluded
    assert data[0]["distance_km"] < data[1]["distance_km"]
    assert "near-a" in names[0] and "far-b" in names[1]


def test_nearby_requires_valid_coords():
    resp = client.get("/api/v1/public/branches/nearby")
    assert resp.status_code == 422
    resp2 = client.get("/api/v1/public/branches/nearby", params={"lat": 95, "lon": 51})
    assert resp2.status_code == 422


def test_nearby_does_not_persist_location():

    from app.core.db import engine
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    _branch(hok, "anon-x", 35.75, 51.41, status="published")
    before = _audit_count(engine)
    resp = client.get(
        "/api/v1/public/branches/nearby", params={"lat": 35.7501, "lon": 51.4101}
    )
    assert resp.status_code == 200
    assert _audit_count(engine) == before  # nothing recorded for the map query


def _audit_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM audit.audit_logs WHERE action LIKE '%nearby%'")
        ).scalar_one()


def test_open_today_flag_in_nearby_response():
    token, _ = grant(_phone(), "system_admin")
    hok = h(token)
    _branch(hok, "hours-a", 35.75, 51.41, status="published", hours={"0": [["00:00", "23:59"]]})
    _branch(hok, "hours-b", 35.74, 51.40, status="published", hours=None)
    resp = client.get("/api/v1/public/branches/nearby", params={"lat": 35.75, "lon": 51.41})
    flags = {b["open_today"] for b in resp.json()["data"]}
    assert flags <= {True, False, None}
    assert True in flags or None in flags  # 24h branch or unknown-hours branch


@pytest.mark.parametrize(
    "hours, weekday, clock, expected",
    [
        ({"0": [["09:00", "17:00"]]}, 0, time(10, 0), True),
        ({"0": [["09:00", "17:00"]]}, 0, time(20, 0), False),
        ({"0": [["09:00", "17:00"]]}, 1, time(10, 0), False),  # other day
        ({"2": [["08:00", "12:00"], ["14:00", "18:00"]]}, 2, time(13, 0), False),
        ({"2": [["08:00", "12:00"], ["14:00", "18:00"]]}, 2, time(15, 0), True),
        (None, 0, time(10, 0), None),  # unknown hours
    ],
)
def test_is_open_now_pure(hours, weekday, clock, expected):
    assert is_open_now(hours, weekday, clock) == expected


def test_haversine_known_distance():
    # تهران تا کرج ~ 39-42km; loose bounds keep the test stable
    d = haversine_km(35.6892, 51.3890, 35.8355, 50.9915)
    assert 35.0 < d < 45.0
