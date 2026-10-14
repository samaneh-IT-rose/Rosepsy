import json, urllib.request
oa = json.load(urllib.request.urlopen("http://localhost:8000/openapi.json"))
print("=== PATHS ===")
for p, item in oa["paths"].items():
    if "rule" in p.lower() or "exception" in p.lower():
        for m, op in item.items():
            if m in ("get", "post", "put", "patch", "delete"):
                print(m.upper(), p, "->", op.get("summary"))
print("=== SCHEMAS ===")
for name, sch in oa["components"]["schemas"].items():
    if "rule" in name.lower() or "exception" in name.lower():
        print(name, ":", json.dumps(sch, ensure_ascii=False))
