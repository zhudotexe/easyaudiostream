import sys
import time
from pathlib import Path

from pydub import AudioSegment

sys.path.append(str(Path(__file__).parents[1].absolute()))

from easyaudiostream.audio import FFMPEGAudioManager, PyAudioAudioManager, PyDubAudioManager

test_fp = Path(__file__).parent / "test_audio.mp3"


def load_test_audio() -> bytes:
    """Load the test audio, resample to 24kHz PCM"""
    audio = AudioSegment.from_file(test_fp)
    return audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).raw_data


def fast_stream(audio: bytes):
    yield audio


def choppy_stream(audio: bytes):
    # 16b, 24kHz = 48B/sec
    for sec in range(0, len(audio), 48000):
        yield audio[sec : sec + 48000]
        time.sleep(0.95)


def choppy_slow_stream(audio: bytes):
    # 16b, 24kHz = 48B/sec
    for sec in range(0, len(audio), 48000 * 5):
        for i in range(0, 48000 * 5, 48000):
            yield audio[sec + i : sec + i + 48000]
            time.sleep(0.95)

        # oh no, my bytes
        time.sleep(3)


def main():
    audio = load_test_audio()
    pyaudio_manager = PyAudioAudioManager()
    ffmpeg_manager = FFMPEGAudioManager()
    pydub_manager = PyDubAudioManager()
    # change me for tests
    stream = choppy_stream(audio)
    manager = ffmpeg_manager
    # end
    for data in stream:
        segment = AudioSegment(data=data, sample_width=2, channels=1, frame_rate=24000)
        manager.play(segment)

    time.sleep(300)


if __name__ == "__main__":
    main()
