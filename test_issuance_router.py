try:
    print("Importing issuance router...")
    from app.admin.api.issuance import router
    print("Import successful!")
    for route in router.routes:
        print(f"{route.methods} {route.path}")
except Exception as e:
    print(f"Error: {e}")
except BaseException as e:
    print(f"BaseException: {type(e)}")
