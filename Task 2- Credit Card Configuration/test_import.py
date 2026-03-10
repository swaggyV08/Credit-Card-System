try:
    import app.main
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
