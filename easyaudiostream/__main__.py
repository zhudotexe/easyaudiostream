import sys

from . import __version__, _capabilities, mic

if __name__ == "__main__":
    print(f"easyaudiostream v{__version__}")
    print(f"Python {sys.version} on {sys.platform}")
    print(f"FFMPEG installed: {_capabilities.has_ffmpeg}")
    print(f"PyAudio installed: {_capabilities.has_pyaudio}")

    print()
    if not _capabilities.has_pyaudio:
        print("PyAudio is not installed -- mic recording utilities are not enabled.")
    else:
        print("===== Microphones on system =====")
        mic.list_mics()
