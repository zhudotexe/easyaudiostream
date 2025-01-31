from easyaudiostream import get_mic_stream, list_mics, play_raw_audio


def main(mic_id):
    stream = get_mic_stream(mic_id)
    for frame in stream:
        play_raw_audio(frame)


if __name__ == "__main__":
    list_mics()
    try:
        m = int(input("Enter mic ID to use [0]: "))
    except ValueError:
        m = 0
    main(m)
