import io
import queue
import subprocess
import threading
import time
import warnings
from typing import Iterable

from pydub import AudioSegment

from . import _capabilities


# ===== output =====
class AudioManagerBase:
    def play(self, segment: AudioSegment):
        raise NotImplementedError


class PyAudioAudioManager(AudioManagerBase):
    """Audio manager using a PyAudio stream"""

    def __init__(self):
        self.q = queue.Queue()
        self.thread = None
        self.stream = None

    def play(self, segment: AudioSegment):
        import pyaudio

        # resample the segment to raw 24khz pcm
        pcm_audio = segment.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        # push the segment onto the queue
        self.q.put(pcm_audio)
        # open the stream
        if self.stream is None:
            p = pyaudio.PyAudio()
            self.stream = p.open(
                format=p.get_format_from_width(pcm_audio.sample_width),
                channels=pcm_audio.channels,
                rate=pcm_audio.frame_rate,
                output=True,
            )
        # start the thread to handle the queue
        if self.thread is None:
            self.thread = threading.Thread(target=self._thread_entrypoint, daemon=True)
            self.thread.start()

    def _thread_entrypoint(self):
        from pydub.utils import make_chunks

        # hack: 100ms sleep before reading from q to avoid startup crunchiness
        time.sleep(0.1)
        while True:
            segment = self.q.get()
            for chunk in make_chunks(segment, 500):
                self.stream.write(chunk.raw_data)


class FFMPEGAudioManager(AudioManagerBase):
    """Audio manager using a ffplay process with a byte pipe"""

    def __init__(self):
        self.q = queue.Queue()
        self.ffplay = None
        self.thread = None

    def play(self, segment: AudioSegment):
        # resample the segment to raw 24khz pcm
        pcm_audio = segment.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        # push the segment onto the queue
        self.q.put(pcm_audio)
        # open the stream
        if self.ffplay is None:
            self.ffplay = subprocess.Popen(
                ["ffplay", "-nodisp", "-f", "s16le", "-ar", "24000", "-acodec", "pcm_s16le", "-i", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        # start the thread to handle the queue
        if self.thread is None:
            self.thread = threading.Thread(target=self._thread_entrypoint, daemon=True)
            self.thread.start()

    def _thread_entrypoint(self):
        # 50ms of silence
        # 16b frame * 24k fps = 2 * 24000 / 20 bytes = 2400B
        silence_bytes = b"\0\0" * 2400
        playing_until = time.perf_counter()
        while True:
            try:
                # if we have a segment, write it and wait for its duration before writing more
                segment = self.q.get(block=False)
                self.ffplay.stdin.write(segment.raw_data)
                self.ffplay.stdin.flush()
                playing_until += segment.duration_seconds
            except queue.Empty:
                now = time.perf_counter()
                # if we are currently playing audio, wait a bit and check if we have more to do once it's half done
                if playing_until > now:
                    remaining = playing_until - now
                    time.sleep(max(min(0.05, remaining), remaining / 2))
                # otherwise write silence
                else:
                    # no lag time needed - processing should happen within 41us so the next frame is ready in time
                    # we need to write silence because of https://superuser.com/questions/1859542/ffplay-reading-pcm-data-from-pipe-pause-when-no-data-available-instead-of-cont
                    self.ffplay.stdin.write(silence_bytes)
                    self.ffplay.stdin.flush()
                    time.sleep(0.05)
                    playing_until = time.perf_counter()


class PyDubAudioManager(AudioManagerBase):
    """Fallback audio manager using pydub's default play if we don't have ffplay or pyaudio"""

    def __init__(self):
        self.pending_segment: AudioSegment | None = None
        self.thread = None
        self._has_pending = threading.Event()
        self._lock = threading.Lock()

    def play(self, segment: AudioSegment):
        # start the thread to play in the bg
        if self.thread is None:
            self.thread = threading.Thread(target=self._thread_entrypoint, daemon=True)
            self.thread.start()
        # then do bookkeeping
        with self._lock:
            if self.pending_segment is not None:
                self.pending_segment += segment
            else:
                self.pending_segment = segment
                self._has_pending.set()

    def _thread_entrypoint(self):
        from pydub.playback import play

        while True:
            self._has_pending.wait()
            with self._lock:
                segment = self.pending_segment
                self.pending_segment = None
                self._has_pending.clear()
            play(segment)


if _capabilities.has_pyaudio:
    _global_audio_manager = PyAudioAudioManager()
elif _capabilities.has_ffmpeg:
    _global_audio_manager = FFMPEGAudioManager()
else:
    warnings.warn(
        "You do not have PyAudio or ffmpeg installed. Playback may have choppy output. We recommend installing"
        " PyAudio or ffmpeg for best playback performance."
    )
    _global_audio_manager = PyDubAudioManager()


def play_audio(audio_bytes: bytes):
    """
    Play the given audio at the next available opportunity, using a global audio queue.

    .. note::
        This function will return immediately - it just puts the audio on a queue!
        If your program ends after calling this function, the audio will not play - you might need to ``sleep(...)``.
    """
    # Load the audio file from the byte stream
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
    _global_audio_manager.play(audio)


def play_raw_audio(audio_bytes: bytes, *, sample_width: int = 2, channels: int = 1, frame_rate: int = 24000):
    """
    Play the given raw audio at the next available opportunity, using a global audio queue.

    .. warning::
        If you aren't sure which function to use, use :func:`.play_audio` instead! Playing raw audio bytes is
        a minor optimization that avoids converting the audio format, but requires a specific input format.

    .. note::
        This function will return immediately - it just puts the audio on a queue!
        If your program ends after calling this function, the audio will not play - you might need to ``sleep(...)``.

    By default, this method accepts raw 16 bit PCM audio at 24kHz, 1 channel, little-endian. You can control the
    expected format of the raw audio using the keyword arguments.
    """
    audio = AudioSegment(data=audio_bytes, sample_width=sample_width, channels=channels, frame_rate=frame_rate)
    _global_audio_manager.play(audio)


def play_stream(audio_stream: Iterable[bytes]):
    """
    Consume bytes from the audio stream and play them.

    .. note::
        This function will return as soon as the stream is exhausted!
        If your program ends after calling this function, the audio will not play - you might need to ``sleep(...)``.
    """
    for audio_bytes in audio_stream:
        play_audio(audio_bytes)


def play_raw_stream(
    audio_stream: Iterable[bytes], *, sample_width: int = 2, channels: int = 1, frame_rate: int = 24000
):
    """
    Consume PCM audio bytes from the audio stream and play them.

    .. warning::
        If you aren't sure which function to use, use :func:`.stream_audio` instead! Playing raw audio bytes is
        a minor optimization that avoids converting the audio format, but requires a specific input format.

    .. note::
        This function will return as soon as the stream is exhausted!
        If your program ends after calling this function, the audio will not play - you might need to ``sleep(...)``.

    By default, this method accepts raw 16 bit PCM audio at 24kHz, 1 channel, little-endian. You can control the
    expected format of the raw audio using the keyword arguments.
    """
    for audio_bytes in audio_stream:
        play_raw_audio(audio_bytes, sample_width=sample_width, channels=channels, frame_rate=frame_rate)
