import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "pytest", "tests/unit/services/engines/"], capture_output=True, text=True)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("RETURN CODE:", result.returncode)
