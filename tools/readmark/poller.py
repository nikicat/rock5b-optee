# poller.py <logfile>: read /proc/readmark once a second, append with fsync. No exec, no module loads.
import os, sys, time
log = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
t0 = time.time()
while True:
    try:
        fd = os.open("/proc/readmark", os.O_RDONLY); v = os.read(fd, 64).decode().strip(); os.close(fd)
    except OSError as e:
        v = f"err {e.errno}"
    os.write(log, f"{time.time()-t0:5.1f}s stage={v}\n".encode()); os.fsync(log)
    time.sleep(1)
