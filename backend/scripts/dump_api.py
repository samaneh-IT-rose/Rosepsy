import json, re, urllib.request

oa = json.load(urllib.request.urlopen("http://localhost:8000/openapi.json"))
pat = re.compile(r"hold|appointment|order|payment|invoice|service|availab|consultant|consent|clinical|encounter")
paths = {k: v for k, v in oa["paths"].items() if pat.search(k)}

refs = set()
slim = {}
for p, item in paths.items():
    entry = {}
    if "parameters" in item:
        entry["parameters"] = item["parameters"]
    for m in ("get", "post", "patch", "delete"):
        if m in item:
            op = {}
            if "summary" in item[m]:
                op["summary"] = item[m]["summary"]
            rb = item[m].get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            if "$ref" in rb:
                name = rb["$ref"].split("/")[-1]
                refs.add(name)
                op["body"] = name
            entry[m] = op
    slim[p] = entry

schemas = {n: oa["components"]["schemas"][n] for n in sorted(refs)}
out = {"paths": slim, "schemas": schemas}
with open("docs/booking-api-dump.json", "w", encoding="utf8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("saved -> docs/booking-api-dump.json")
