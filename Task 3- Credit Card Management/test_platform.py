import platform
print("Importing platform...")
try:
    print("Calling platform.uname()...")
    u = platform.uname()
    print(f"Uname: {u}")
except Exception as e:
    print(f"Error: {e}")
print("Done!")
