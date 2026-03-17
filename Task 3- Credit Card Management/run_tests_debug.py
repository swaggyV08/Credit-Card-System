import subprocess
import sys

def run_tests():
    print("Running tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/api/card_management/test_lifecycle_v3.py", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)
    print(f"Exit Code: {result.returncode}")

if __name__ == "__main__":
    run_tests()
