import urllib.request
import json
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json") as response:
        data = json.loads(response.read().decode())
        paths = data.get("paths", {})
        if "/admin/credit-applications/{application_id}/evaluate" in paths:
            print("EVALUATE ENDPOINT FOUND IN OPENAPI")
        else:
            print("EVALUATE ENDPOINT NOT FOUND. AVAILABLE POST ROUTES:", [p for p, methods in paths.items() if 'post' in methods])
except Exception as e:
    print("Error:", e)
