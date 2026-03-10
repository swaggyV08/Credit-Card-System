import subprocess
import sys

with open("pytest_results_final.txt", "w") as f:
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/unit/services/engines/", "-v", "-p", "no:warnings"], stdout=f, stderr=subprocess.STDOUT, text=True)
print(f"Pytest finished with return code: {result.returncode}")
