import json, time, urllib.request, urllib.error

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

def find_by_key(o, needle):
    if isinstance(o, dict):
        for k, v in o.items():
            if needle in k.lower() and isinstance(v, str):
                return v
            r = find_by_key(v, needle)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_by_key(v, needle)
            if r:
                return r
    return None

st, r1 = call("POST", "/auth/otp/request", body={"phone": PHONE})
chal = r1["data"]["challenge_id"]
st, ver = call("POST", "/auth/otp/verify", body={"phone": PHONE, "challenge_id": chal, "code": "123456"})
tok = ver["data"]["access_token"]
print("login", st)

st, cons = call("GET", "/consultants", token=tok)
cid = cons["data"][0]["id"]
st, svcs = call("GET", "/services", token=tok)
sid = svcs["data"][0]["id"]
st, av = call("GET", "/consultants/" + cid + "/availability?service_id=" + sid, token=tok)
dates = av["data"]["dates"]
slots = []
for d in sorted(dates.keys()):
    for s in dates[d]:
        slots.append(s["start"])
print("slots", len(slots))

hold = None
for s in slots[:20]:
    st, h = call("POST", "/booking-holds", token=tok, body={"consultant_id": cid, "service_id": sid, "start_at": s})
    if 200 <= st < 300:
        hold = h
        break
    print("hold skip", st)
if not hold:
    raise SystemExit("no free slot")
hid = hold["data"]["id"]
print("hold ok")

st, appt = call("POST", "/appointments", token=tok, body={"hold_id": hid})
apid = appt["data"]["id"]
print("appt ok")

st, order = call("POST", "/orders", token=tok, body={"appointment_id": apid}, headers={"Idempotency-Key": "inv-probe-" + str(int(time.time()))})
oid = order["data"]["id"]
print("ORDER_FULL", j(order["data"]))

st, pay = call("POST", "/payments/start", token=tok, body={"order_id": oid})
print("PAY_START_FULL", j(pay))

paid_order = None
for i in range(3):
    time.sleep(1)
    st, o = call("GET", "/orders/" + oid, token=tok)
    print("poll", i, o["data"].get("status"))
    if o["data"].get("status") in ("paid", "failed"):
        paid_order = o
        break

if not paid_order:
    ref = find_by_key(pay, "ref") or find_by_key(pay, "token") or oid
    st, cb = call("POST", "/payments/callback", body={"gateway_ref": ref, "result": "success"})
    print("CALLBACK_FULL", j(cb))
    for i in range(3):
        time.sleep(1)
        st, o = call("GET", "/orders/" + oid, token=tok)
        print("poll2", i, o["data"].get("status"))
        if o["data"].get("status") in ("paid", "failed"):
            paid_order = o
            break

print("ORDER_FINAL_FULL", j(paid_order))

pid = find_by_key(pay, "payment")
if pid and len(pid) == 36:
    st, prec = call("GET", "/payments/" + pid, token=tok)
    print("PAYMENT_RECORD", st, j(prec))

