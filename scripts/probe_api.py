import json, re, urllib.request, urllib.error

BASE = "http://localhost:8000/api/v1"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
PHONE = "09120000000"

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

results = {}

def step(name, res):
    results[name] = {"status": res[0], "body": res[1]}
    print(f"=== {name} -> {res[0]} ===")
    print(json.dumps(res[1], ensure_ascii=False, indent=1))

def find_token(o):
    if isinstance(o, dict):
        for v in o.values():
            r = find_token(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_token(v)
            if r:
                return r
    elif isinstance(o, str) and o.startswith("ey") and o.count(".") == 2:
        return o
    return None

def find_id(o):
    if isinstance(o, dict):
        v0 = o.get("id")
        if isinstance(v0, str) and UUID_RE.match(v0):
            return v0
        for v in o.values():
            r = find_id(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_id(v)
            if r:
                return r
    return None

def find_named_uuid(o, needle):
    if isinstance(o, dict):
        for k, v in o.items():
            if needle in k.lower() and isinstance(v, str) and UUID_RE.match(v):
                return v
        for v in o.values():
            r = find_named_uuid(v, needle)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_named_uuid(v, needle)
            if r:
                return r
    return None

start_val = None

def find_start(o):
    global start_val
    if start_val:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            if "start" in k.lower() and isinstance(v, str) and "T" in v:
                start_val = v
                return
            find_start(v)
    elif isinstance(o, list):
        for v in o:
            find_start(v)

step("otp_request", call("POST", "/auth/otp/request", body={"phone": PHONE}))
chal = results["otp_request"]["body"]["data"]["challenge_id"]
st, ver = call("POST", "/auth/otp/verify", body={"phone": PHONE, "challenge_id": chal, "code": "123456"})
step("verify", (st, ver))
tok = (ver.get("data") or {}).get("access_token") if st == 200 else None
print("TOKEN:", "OK" if tok else "NOT FOUND")
if not tok:
    raise SystemExit

step("services", call("GET", "/services", token=tok))
step("consultants", call("GET", "/consultants", token=tok))
step("my_appointments", call("GET", "/appointments", token=tok))
step("my_consents", call("GET", "/consents", token=tok))
step("my_record", call("GET", "/clinical-records/me", token=tok))

cid = find_id(results["consultants"]["body"])
sid = find_id(results["services"]["body"])
print("consultant_id:", cid)
print("service_id:", sid)
st, av = call("GET", f"/consultants/{cid}/availability?service_id={sid}", token=tok)
step("availability", (st, av))
if st == 422:
    step("availability_no_params", call("GET", f"/consultants/{cid}/availability", token=tok))

find_start(results["availability"]["body"])
print("slot start:", start_val)

if cid and sid and start_val:
    step("hold", call("POST", "/booking-holds", token=tok,
                      body={"consultant_id": cid, "service_id": sid, "start_at": start_val}))
    hid = find_id(results["hold"]["body"])
    print("hold_id:", hid)
    if hid:
        step("appointment", call("POST", "/appointments", token=tok, body={"hold_id": hid}))
        apid = find_id(results["appointment"]["body"])
        print("appointment_id:", apid)
        if apid:
            step("order", call("POST", "/orders", token=tok, body={"appointment_id": apid},
                               headers={"Idempotency-Key": "probe-0001"}))
            oid = find_id(results["order"]["body"])
            print("order_id:", oid)
            if oid:
                step("pay_start", call("POST", "/payments/start", token=tok, body={"order_id": oid}))
                step("order_after_start", call("GET", f"/orders/{oid}", token=tok))
                iid = find_named_uuid(results["order_after_start"]["body"], "invoice")
                print("invoice_id:", iid)
                if iid:
                    step("invoice", call("GET", f"/invoices/{iid}", token=tok))

with open(r"D:\projects\rose-clinic\docs\api-probe.json", "w", encoding="utf8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print("saved -> docs/api-probe.json")


