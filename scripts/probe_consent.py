import json, urllib.request, urllib.error

BASE = "http://localhost:8000/api/v1"
PHONE = "09129990003"

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

def j(x):
    return json.dumps(x, ensure_ascii=False)

st, r1 = call("POST", "/auth/otp/request", body={"phone": PHONE})
chal = r1["data"]["challenge_id"]
st, ver = call("POST", "/auth/otp/verify", body={"phone": PHONE, "challenge_id": chal, "code": "123456"})
tok = ver["data"]["access_token"]
print("login", st)

st, cons = call("GET", "/consents", token=tok)
print("MY_CONSENTS", st, j(cons))

st, rec = call("GET", "/clinical-records/me", token=tok)
print("MY_RECORD", st, j(rec))
