try:
    import app.api.auth
    print("app.api.auth imported successfully")
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    from app.main import app
    print("app.main imported successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
