from app.main import app

target = "/admin/credit-applications/{application_id}/evaluate"
found = False
for route in app.routes:
    if hasattr(route, 'path') and route.path == target:
        found = True
        print(f"FOUND: {route.methods} {route.path}")
        break

if not found:
    print(f"NOT FOUND: {target}")
    # Print all for debugging if not found
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"  {route.path}")
