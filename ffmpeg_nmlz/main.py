import re
import subprocess
from pathlib import Path
from subprocess import Popen
from typing import Optional, Tuple
from argparse import ArgumentParser

VOLUME_REGEX = re.compile(r'max_volume: ([\-\d.]+) dB\n')


def ffmpeg_get_max_volume(in_path: str) -> float:
    ffmpeg = Popen(
        [
            'ffmpeg',
            '-i', in_path,
            '-map', '0:a:0',
            '-af', 'volumedetect',
            '-f', 'null', 'null'
        ],
        encoding='utf-8',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    stdout, _ = ffmpeg.communicate()

    m = VOLUME_REGEX.search(stdout)
    max_volume = float(m.group(1))

    return max_volume


def ffmpeg_convert_to_wav(in_path: str, out_path: str, volume: float) -> None:
    if not out_path.endswith('.wav'):
        raise ValueError('out_path must end with ".wav".')

    Popen(
        [
            'ffmpeg',
            '-y',
            '-i', str(in_path),
            '-map', '0:a:0',
            '-af', f'volume={volume:.1f}dB',
            '-c:a', 'pcm_s16le',
            '-f', 'wav',
            str(out_path),
        ],
        encoding='utf-8',
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).wait()


def get_path(in_path_str: str, out_path_str: Optional[str] = None) -> Tuple[Path, Path]:
    in_path = Path(in_path_str).resolve(strict=True)

    if out_path_str is None:
        if in_path.suffix == '.wav':
            out_path = in_path.parent / f'{in_path.stem}-1.wav'
        else:
            out_path = in_path.parent / f'{in_path.stem}.wav'
    else:
        out_path = Path(out_path_str)
        if str(in_path) == str(out_path):
            out_path = in_path.parent / f'{in_path.stem}-1.wav'
        if out_path.suffix != '.wav':
            raise ValueError('Output path must end with .wav')

    out_path = out_path.resolve(strict=False)

    return in_path, out_path


def normalize(in_path_str: str, out_path_str: Optional[str] = None) -> None:
    in_path, out_path = get_path(in_path_str, out_path_str)

    max_volume = ffmpeg_get_max_volume(str(in_path))
    print(f'    Max volume: {max_volume} dB')

    target_volume = max(abs(max_volume), 0)

    print('    Encoding...\n')
    ffmpeg_convert_to_wav(str(in_path), str(out_path), target_volume)


def main():
    parser = ArgumentParser()
    parser.add_argument('input', nargs='+')

    args = parser.parse_args()
    for i, in_file in enumerate(args.input):
        print(f'> File {i+1}: {in_file}')
        normalize(in_file)


if __name__ == '__main__':
    main()
