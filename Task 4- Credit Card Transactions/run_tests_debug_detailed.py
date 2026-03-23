import subprocess
import sys

def run_tests():
    print("Running tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/api/card_management/test_lifecycle_v3.py", "-vv", "--tb=long"],
        capture_output=True,
        text=True
    )
    with open("pytest_detailed_output.txt", "w", encoding="utf-8") as f:
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)
    print(f"Exit Code: {result.returncode}")

if __name__ == "__main__":
    run_tests()
