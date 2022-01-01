import os
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from subprocess import Popen
from typing import Optional, NamedTuple


class FfmpegNmlzError(RuntimeError):
    '''Errors that comes from current application.'''


class FormatConfig(NamedTuple):
    encoder: str
    extension: str
    bitrate: Optional[str]


class SingleFileConfig(NamedTuple):
    in_path: Path
    out_path: Path


ROOT = Path('.')
VOLUME_REGEX = re.compile(r'max_volume: ([\-\d.]+) dB\n')
RE_PRESET = re.compile(r'([a-zA-Z]+)(\d+)?')

# Mapping: Preset name -> (Encoder, Default file extension, Default bitrate)
PRESET_INFO = {
    'm4a': FormatConfig('libfdk_aac', 'm4a', '128K'),
    'aac': FormatConfig('libfdk_aac', 'm4a', '128K'),
    'mp3': FormatConfig('libmp3lame', 'mp3', '192K'),
    'opus': FormatConfig('libopus', 'opus', '128K'),
    'ogg': FormatConfig('libvorbis', 'ogg', '160K'),
    'wav': FormatConfig('pcm_s16le', 'wav', None),
    'flac': FormatConfig('flac', 'flac', None),
}


def call_ffmpeg(params: list[str]) -> str:
    try:
        ffmpeg = Popen(
            params,
            encoding='utf-8',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        raise FfmpegNmlzError('FFmpeg is not installed. Please install FFmpeg first.')
    except:
        raise FfmpegNmlzError('Failed to start FFmpeg. Please check your FFmpeg installation.')

    stdout, _ = ffmpeg.communicate()
    if ffmpeg.returncode != 0:
        raise FfmpegNmlzError('FFmpeg exited abnormally.')

    return stdout


def ffmpeg_get_max_volume(in_path: str) -> float:
    stdout = call_ffmpeg([
        'ffmpeg',
        '-i', in_path,
        '-map', '0:a:0',
        '-af', 'volumedetect',
        '-f', 'null', 'null'
    ])

    m = VOLUME_REGEX.search(stdout)
    max_volume = float(m.group(1))

    return max_volume


def ffmpeg_convert_with_volume_filter(
        in_path: str, out_path: str,
        volume: float, format_config: FormatConfig
) -> None:
    params = [
        'ffmpeg',
        '-y',
        '-i', in_path,
        '-map', '0:a:0',
        '-af', f'volume={volume:.1f}dB',
        '-c:a', format_config.encoder,
    ]
    if format_config.bitrate is not None:
        params += ['-b:a', format_config.bitrate]
    params.append(out_path)

    call_ffmpeg(params)


def get_out_path(output_dir: Path, format_config: FormatConfig, in_path: Path) -> Path:
    return output_dir / f'{in_path.stem}-1.{format_config.extension}'


def parse_file_input(input_item: str) -> SingleFileConfig:
    in_path = Path(input_item).resolve(strict=True)
    out_path = in_path.parent / f'{in_path.stem}.wav'
    return SingleFileConfig(in_path, out_path)


def verify_and_canonicanize_path(path: Path) -> Path:
    try:
        path = path.resolve(strict=True)
        f = path.open('rb')
        f.read(1)
        f.close()
    except:
        raise FfmpegNmlzError(f'Failed to open file: {path}')

    return path


def verify_and_prepare_args(args) -> tuple[Path, FormatConfig, list[Path]]:
    # Prepare output directory
    try:
        output_dir = Path(args.output_dir)
        if not output_dir.is_dir():
            os.makedirs(str(output_dir), exist_ok=True)
        output_dir = output_dir.resolve(strict=True)
    except:
        # Print message to stderr
        raise FfmpegNmlzError(f'Unable to create output directory: {args.output_dir}')

    # Verify input items, and find input files (may contain wildcards)
    encoder, extension, bitrate = PRESET_INFO['wav']
    input_patterns: list[str] = []

    # Find input items which are actually presets
    for input_item in args.inputs:
        match_res = RE_PRESET.fullmatch(input_item)
        if match_res is not None:
            # The item might be a preset
            preset_name, parsed_bitrate = match_res.groups()
            if preset_name in PRESET_INFO:
                # The item is a preset
                encoder, extension, bitrate = PRESET_INFO[preset_name]
                if parsed_bitrate is not None:
                    bitrate = f'{parsed_bitrate}K'
            else:
                # The item looks like a preset, but we can't recognize it
                input_patterns.append(input_item)
        else:
            # The item is a file or pattern
            input_patterns.append(input_item)

    if args.extension is not None:
        extension = args.extension

    input_files: list[Path] = []

    # Verify that whether files exists
    for pattern in input_patterns:
        if '*' in pattern or '?' in pattern:
            # input_file is a pattern
            has_file = False

            for input_file in ROOT.glob(pattern):
                has_file = True
                input_files.append(verify_and_canonicanize_path(input_file))

            if not has_file:
                raise FfmpegNmlzError(f'No files found for pattern: {pattern}')
        else:
            # input_file is an actual file
            input_files.append(verify_and_canonicanize_path(Path(pattern)))

    # Remove duplicate files while keeping input order
    input_files = list(({k: None for k in input_files}).keys())

    return output_dir, FormatConfig(encoder, extension, bitrate), input_files


def get_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument(
        '-d', '--output-dir',
        type=str,
        help='Specify the output directory where normalized audio file is in.',
        metavar='output_dir',
        default='.',
    )
    parser.add_argument(
        '-e', '--extension',
        type=str,
        help='Specify the extension of output file(s).',
        metavar='extension',
        default=None,
    )
    parser.add_argument(
        'inputs',
        nargs='+',
        help='''Input files. Wildcasts like "files/*.wav" are allowed.''',
        metavar='inputs',
    )
    return parser


def do_normalizing():
    args = get_parser().parse_args()
    output_dir, format_config, input_paths = verify_and_prepare_args(args)

    for i, in_path in enumerate(input_paths):
        print(f'> File {i + 1}: {in_path.name}')
        out_path = get_out_path(output_dir, format_config, in_path)

        max_volume = ffmpeg_get_max_volume(str(in_path))
        print(f'    Max volume: {max_volume} dB')

        target_volume = max(abs(max_volume), 0)

        print('    Encoding...\n')
        ffmpeg_convert_with_volume_filter(
            str(in_path), str(out_path),
            target_volume, format_config
        )


def main():
    try:
        do_normalizing()
    except FfmpegNmlzError as e:
        print(f'\nERROR: {e.args[0]}', file=sys.stderr)


if __name__ == '__main__':
    main()
