import platform
import collections
UnameResult = collections.namedtuple('uname_result', ['system', 'node', 'release', 'version', 'machine', 'processor'])
platform.uname = lambda: UnameResult('Windows', 'node', '10', '10.0.19041', 'AMD64', 'Intel64 Family 6 Model 158 Stepping 10')

try:
    from app.main import app
    print("App imported successfully. Generating OpenAPI schema...")
    schema = app.openapi()
    print("Schema generated!")
    
    paths = schema.get("paths", {})
    target = "/admin/credit-applications/{application_id}/evaluate"
    if target in paths:
        print(f"SUCCESS: Found {target} in OpenAPI paths.")
    else:
        print(f"FAILURE: {target} NOT FOUND in OpenAPI paths.")
        print("Available paths:")
        for p in paths:
            print(f"  - {p}")
            
except Exception as e:
    import traceback
    print(f"Error generating OpenAPI schema: {e}")
    traceback.print_exc()
