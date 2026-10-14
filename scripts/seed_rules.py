import json, urllib.request, urllib.error

BASE = "http://localhost:8000/api/v1"
PHONE = "09129990002"

def call(method, path, token=None, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

st, req = call("POST", "/auth/otp/request", body={"phone": PHONE})
chal = req["data"]["challenge_id"]
st, ver = call("POST", "/auth/otp/verify", body={"phone": PHONE, "challenge_id": chal, "code": "123456"})
tok = ver["data"]["access_token"]
print("login ->", st)

st, cons = call("GET", "/consultants", token=tok)
cid = cons["data"][0]["id"]
st, svcs = call("GET", "/services", token=tok)
sid = svcs["data"][0]["id"]
print("consultant:", cid)
print("service:", sid)

rules = [{"weekday": d, "start_time": "09:00", "end_time": "17:00"} for d in range(7)]
st, r = call("PUT", "/consultants/" + cid + "/availability-rules", token=tok, body={"rules": rules})
print("PUT rules ->", st)

st, av = call("GET", "/consultants/" + cid + "/availability?service_id=" + sid, token=tok)
dates = (av.get("data") or {}).get("dates", {})
print("dates count:", len(dates))
for d, slots in list(dates.items())[:2]:
    print("SAMPLE", d, json.dumps(slots, ensure_ascii=False)[:400])
