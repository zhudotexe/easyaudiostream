import subprocess

ffplay_available = (
    subprocess.run(["ffplay", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
)

try:
    import pyaudio
except ImportError:
    has_pyaudio = False
else:
    has_pyaudio = True
