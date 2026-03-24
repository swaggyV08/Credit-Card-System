import subprocess
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
result = subprocess.run(["pytest", "-v", "--tb=short"], capture_output=True, text=True, encoding="utf-8")
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("RC:", result.returncode)
