import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1].absolute()))

from easyaudiostream.audio import play_audio

test_fp = Path(__file__).parent / "test_audio.mp3"


def main():
    with open(test_fp, "rb") as f:
        audio_bytes = f.read()

    play_audio(audio_bytes)

    time.sleep(300)


if __name__ == "__main__":
    main()
