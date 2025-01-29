import abc
import asyncio
import queue
import threading
import time
from typing import AsyncIterable, Iterable

from . import _capabilities

if _capabilities.has_pyaudio:
    import pyaudio

    class PyAudioInputManagerBase(abc.ABC):
        """Audio manager using a PyAudio stream. This class should NOT be constructed manually."""

        def __init__(self, mic_id: int | None):
            # init pyaudio, create a recording stream
            p = pyaudio.PyAudio()
            self.stream = p.open(
                format=p.get_format_from_width(2),
                channels=1,
                rate=24000,
                frames_per_buffer=1200,
                input=True,
                input_device_index=mic_id,
            )

            # launch thread to start streaming from it
            self.thread = threading.Thread(target=self._thread_entrypoint, daemon=True)
            self.thread.start()

        def _thread_entrypoint(self):
            while True:
                n_available = self.stream.get_read_available()
                if not n_available:
                    time.sleep(0.05)
                    continue
                frame = self.stream.read(n_available, exception_on_overflow=False)
                self._enqueue(frame)

        def _enqueue(self, frame):
            raise NotImplementedError

    class PyAudioInputManagerAsync(PyAudioInputManagerBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.q = asyncio.Queue()
            self.loop = asyncio.get_event_loop()

        def _enqueue(self, frame):
            fut = asyncio.run_coroutine_threadsafe(self.q.put(frame), self.loop)
            fut.result()

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.q.get()

    class PyAudioInputManagerSync(PyAudioInputManagerBase):
        """Audio manager using a PyAudio stream. This class should NOT be constructed manually."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.q = queue.Queue()

        def _enqueue(self, frame):
            self.q.put(frame)

        def __iter__(self):
            return self

        def __next__(self):
            return self.q.get()

    def get_mic_stream(mic_id: int | None) -> Iterable[bytes]:
        """Return an audio stream manager that yields audio frames from the given mic."""
        return PyAudioInputManagerSync(mic_id)

    def get_mic_stream_async(mic_id: int | None) -> AsyncIterable[bytes]:
        """Return an audio stream manager that yields audio frames from the given mic."""
        return PyAudioInputManagerAsync(mic_id)

    def list_mics():
        """Print a list of all microphones connected to this device."""
        p = pyaudio.PyAudio()
        info = p.get_host_api_info_by_index(0)
        n_devices = info.get("deviceCount")
        for i in range(0, n_devices):
            if (p.get_device_info_by_host_api_device_index(0, i).get("maxInputChannels")) > 0:
                print(f"ID: {i} -- {p.get_device_info_by_host_api_device_index(0, i).get('name')}")

else:

    def _missing(*_, **__):
        raise ImportError(
            "You must install PyAudio to record from the mic. You can install this"
            ' with `pip install "easyaudiostream[pyaudio]"`.'
        )

    get_mic_stream = get_mic_stream_async = list_mics = _missing
