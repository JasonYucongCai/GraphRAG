import json, urllib.request, urllib.error, sys

data = json.dumps({"agent_id": "agent_a1", "task": "Say OK only"}).encode()
req = urllib.request.Request(
    "http://127.0.0.3:8000/api/recursive/instruct",
    data=data,
    headers={"Content-Type": "application/json"},
)

try:
    r = urllib.request.urlopen(req, timeout=120)
    resp = json.loads(r.read())
    print("ok:", resp.get("ok"))
    print("answer:", (resp.get("answer", "") or "")[:300])
    print("error:", (resp.get("error", "") or "")[:500])
    print("traceback:", (resp.get("traceback", "") or "")[:1000])
    print("tool_calls:", resp.get("tool_calls"))
except urllib.error.HTTPError as e:
    body = e.read().decode()
    resp = json.loads(body)
    print("HTTP", e.code)
    print("ok:", resp.get("ok"))
    print("error:", (resp.get("error", "") or "")[:500])
    print("traceback:", (resp.get("traceback", "") or "")[:1000])
except Exception as e:
    print("Exception:", e)
