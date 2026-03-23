try:
    from app.api.v1.endpoints.card_management import router as card_router
    print("card_management imported successfully")
except Exception as e:
    import traceback
    print("Error importing card_management:")
    traceback.print_exc()

try:
    from app.api.auth import router as auth_router
    print("auth imported successfully")
except Exception as e:
    import traceback
    print("Error importing auth:")
    traceback.print_exc()

try:
    from app.services.card_management_service import CardManagementService
    print("CardManagementService imported successfully")
except Exception as e:
    import traceback
    print("Error importing CardManagementService:")
    traceback.print_exc()
