import subprocess
import time

proc = subprocess.Popen(["python", "-v", "-c", "import app.main"], stdout=open("verbose.txt", "w"), stderr=subprocess.STDOUT)
time.sleep(10)
proc.terminate()
