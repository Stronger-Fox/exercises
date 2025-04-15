"""Grabs videos from a remote source, cuts and processes them based on a spec.

Dependencies: yt-dlp, ffmpeg, ffprobe (part of ffmpeg)
"""

from dataclasses import dataclass, field
import json
import pathlib as pth
import re
import shutil
import subprocess as sp
import sys
import tempfile
import typing as t
from yt_dlp import YoutubeDL as YDL

TOOL_NAME = pth.Path(__file__).stem


def prepare_args(dct: dict, *, prefixes=('-', None), kvseps=(None, '='), lstsep=','):
    """Formats arguments according to spec.

    Args:
        prefixes: what to put before key at each hierarchy level,
                  i.e. '--' means {'k': 'v'} will be '--k ...'
        kvseps: separators to join keys and values at each level,
                i.e. '=' means {'k': 'v'} will be '--k=v'.
                None means keys and values need to be put as separate elements
        lstsep: separator between value list,
                i.e. ':' means ('coffee', 'is', 'good') becomes 'coffee:is:good'
    """
    def parse_level(data, level=0):
        prefix = prefixes[level]
        kvsep = kvseps[level]
        
        col = []

        for k, v in data.items():
            k = (prefix or '') + k

            if isinstance(v, dict):     # here we go again
                # sure could have done it with no recursion, but must be readable
                subvals = parse_level(v, level + 1)
                for sv in subvals:
                    col += [k, sv] if kvsep is None else [k + kvsep + sv]

                continue

            if isinstance(v, str) and not v:        # empty string -> just the key
                col += [k]
                continue

            if not isinstance(v, str):  # assume something iterable -> join it
                v = lstsep.join(v)

            if isinstance(v, str):
                col += [k, v] if kvsep is None else [k + kvsep + v]
                continue
            
            raise RuntimeError(f"Ewww, '{k}': '{v}'... What are you feeding me with?")

        return col
    
    return parse_level(dct)


# Default arguments to ffprobe in form of an input to `prepare_args`
FFPROBE_ARGS: dict = {
    'loglevel': 'error',        # filter-out unusable data
    'print_format': 'json',     # we'll parse that
    # 'select_streams': 'v',      # only all video streams'
    'show_entries': {
        'stream': '',
        'format': ''
    }
}

def ffprobe_wrap(videofile: pth.Path | str, *,
                 extra_args: dict = {}, is_verbose: bool = True,
                 ffprobe_path: pth.Path | str = 'ffprobe'):
    """A wrapper to call ffprobe and get information on the video file."""
    videofile = pth.Path(videofile)
    assert videofile.exists(), f'File {videofile} not found'

    # We need to use fully-qualified path to executable
    # per https://docs.python.org/3/library/subprocess.html#subprocess.Popen
    ffprobe_bin = shutil.which(ffprobe_path)
    assert ffprobe_bin is not None, f'ffprobe path {ffprobe_path} not found'
    args = [ffprobe_bin]

    kwa = dict(FFPROBE_ARGS)
    kwa.update(extra_args)
    args += prepare_args(kwa, prefixes=('-', None), kvseps=(None, '='), lstsep=',')

    args.append(str(videofile))
    if is_verbose:
        print(' '.join(args), file=sys.stderr)
    out = sp.run(args, capture_output=True, text=True)
    out.check_returncode()

    res = json.loads(out.stdout)
    return res


CUT_REGEXP = r'((?:\.{3})|(?:(?:\d+:)?(?:\d{0,2}:)?\d{0,2}\.?\d{0,3}))'
CUT_REGEXP = re.compile(f'{CUT_REGEXP} - {CUT_REGEXP}')

def concat_format(videofile: pth.Path | str, cuts: t.Iterable[str], *,
                  is_add_header: bool = True) -> str:
    """Formats specified video cut fragments into ffmpeg concat demuxer format.

    Notes:
        See concat demuxer documentation:
          - https://trac.ffmpeg.org/wiki/Concatenate#demuxer
          - https://ffmpeg.org/ffmpeg-formats.html#concat

    Args:
        videofile: Path to input video
        cuts: an iterable with good videofile fragments, where each fragment
            is an str of the form: '[ts_from] - [ts_to]'.

            `[ts_from]` and `[ts_to]` are timestamps in ffmpeg usual format:
            `HH:MM:SS[.frame]` (`.frame` - is the optional frame number in
            that second).

            One of `[ts_from]` or `[ts_to]` can be given as `...`, meaning
            the start or the end of the videofile (`inpoint` or `outpoint`
            will be skipped in the resulting concat output).

            For example, ['... - 00:00:05', '00:00:07 - 00:00:08.12', '00:00:10 - ...']
            will result in video: (start to 5s) + (7s to 8 + 12/fps s) + (10s to end)
        is_add_header: optional argument, defining whether the resulting concat
            should have a usual `ffconcat version 1.0` header at the first line.
            Useful when outputs from numerous files are combined together,
            in the case only the first one needs to have this header.
    Returns:
        An output string, ready to be fed into ffmpeg concat demuxer input
    """
    videofile = pth.Path(videofile)

    lines = []

    if is_add_header:
        lines += ['ffconcat version 1.0']
    lines += [f'# BEGIN Autogenerated portion for file {videofile}']

    if not cuts:    # empty
        lines += [f"file '{videofile}'"]

    for ix, cut in enumerate(cuts, 1):
        match = CUT_REGEXP.fullmatch(cut)
        if not match:
            raise ValueError(f'Wrong cut {cut} for file {videofile}')
        
        begin, end = match.groups()

        lines += [f"file '{videofile}'"]
        if begin != '...':
            lines += [f'inpoint {begin}']
        if end != '...':
            lines += [f'outpoint {end}']
        if ix < len(cuts):  # when not last line
            lines += ['']   # empty line for readability
    
    lines += ['# END autogenerated portion', '']
    
    return '\n'.join(lines)


class VideoSpec:
    url: str
    outfile: pth.Path
    builddir: pth.Path
    metadata: dict | None = None    # @FIXME: avoid very long output via repr
    downloaded: pth.Path | None = None
    info_downloaded: dict | None = None

    is_verbose: bool = False

    _tmpdir: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    # Whether to overwrite files. Class-level default
    is_overwrite: bool = False
    # Template for json filenames
    META_JSON_TPL: str = '{name}.meta.json'
    # Downloaded file name
    DOWNLOADED_TPL: str = '{name}.dl.mkv'

    FFPROBE_PATH: pth.Path = pth.Path('ffprobe')

    def __init__(self, url: str, outfile: pth.Path | str,
                 builddir: pth.Path | str | None = None,
                 *,
                 is_overwrite: bool | None = None,
                 is_verbose: bool | None = None):
        """
        Args:
            url: Where to grab the video from
            outfile: Where to store the result
            builddir: Processing directory.
                      When not provided, creates a tmp directory.
        """
        self.url = url
        self.outfile = pth.Path(outfile)
        # set here, or set to tmpdir lazyly created in _ensure_builddir
        if builddir is not None:
            builddir = pth.Path(builddir)
            builddir.mkdir(exist_ok=True)       # create if doesn't exist
            self.builddir = builddir
            
            # set downloaded as well if found
            dlpath = builddir.joinpath(self.downloaded_name)
            if dlpath.exists():
                self.downloaded = dlpath

        if is_overwrite is not None:    # otherwise use class-level default
            self.is_overwrite = is_overwrite
        if is_verbose is not None:    # otherwise use class-level default
            self.is_verbose = is_verbose

    @property
    def name(self):
        return self.outfile.stem
    
    @property
    def meta_json_name(self):
        return self.META_JSON_TPL.format(name=self.name)
    
    @property
    def downloaded_name(self):
        return self.DOWNLOADED_TPL.format(name=self.name)

    def _ensure_builddir(self):
        if self.builddir is None:
            prefix = f'{TOOL_NAME}_{self.name}_'
            self._tmpdir = tempfile.TemporaryDirectory(prefix=prefix)
            self.builddir = pth.Path(self._tmpdir.name)

    def get_metadata(self, *, shorten: bool = True, is_set_own: bool = True,
                     is_overwrite: bool | None = None):
        """Gets pure metadata for a given entry.

        Note:
            Because of poor YDL architecture, calling this alongside with
            `download()` will cause 2 queries instead of one.
            So, using `download()` is preferrable, as it fills the metadata
            field anyway. This allows to avoid double-querying.
        """

        is_overwrite = is_overwrite if is_overwrite is not None else self.is_overwrite
        json_name = self.meta_json_name
        json_path = (self.builddir is not None and self.builddir.joinpath(json_name))
        
        # Try getting it from build directory if possible
        if not is_overwrite and json_path is not None and json_path.exists():
            with open(json_path, 'r') as f:
                meta = json.load(f)
        else:      # wasn't possible, get it ourselves
            print("@FIXME: REDOWNLOADING METADATA")
            # {'forcejson': True, 'noprogress': True, 'quiet': True, 'simulate': True}
            with YDL({'noprogress': True, 'quiet': True}) as dl:
                meta = dl.extract_info(self.url, download=False, process=False)
            
            # dump it into directory if possible
            if json_path is not None:
                with open(json_path, 'w') as f:
                    json.dump(meta, f, indent=2)

        # filter-out long parts
        if shorten:
            meta = {k: v for k, v in meta.items() if (not k.startswith('_')
                    and not k in ['formats', 'automatic_captions', 'thumbnails']) }

        if is_set_own:
            self.metadata = meta
        
        return meta


    def download(self, *, is_overwrite: bool | None = None):
        """Downloads raw video from a specified remote resource.

        Args:
            is_overwrite: Whether the video file should be overwriten.
                Otherwise, if the downloaded video already exists, no actual
                download is performed and the object state gets filled from
                the exising files.
        """
        is_overwrite = is_overwrite if is_overwrite is not None else self.is_overwrite

        self._ensure_builddir()
        
        # where to put downloaded file
        dlout = self.builddir.joinpath(self.downloaded_name)
        jsonout = self.builddir.joinpath(self.meta_json_name)

        if not dlout.exists() or is_overwrite:
            cfg = {     # --print-to-file "%()j" outfile.meta.json -o "outfile.dl.mkv"
                'outtmpl': {'default': str(dlout)},
                'print_to_file': {'video': [('%()j', str(jsonout))]},
                'noprogress': True,
                'quiet': True
            }
            with YDL(cfg) as dl:
                retcode = dl.download(self.url)

        # metadata should be also present, so fill it
        self.get_metadata(is_set_own=True, is_overwrite=False)
        self.downloaded = dlout
        return dlout, jsonout

    def probe(self, *, extra_args: dict = {},
              is_reprobe: bool | None = None, is_verbose: bool | None = None):
        """Gets the information on a downloaded file using ffprobe"""
        # @TODO: add more processing
        assert (isinstance(self.downloaded, pth.Path) and self.downloaded.exists()
               ), 'Downloaded file does not exist'
                
        is_reprobe = is_reprobe if is_reprobe is not None else self.is_overwrite
        is_verbose = is_verbose if is_verbose is not None else self.is_verbose

        if is_reprobe or self.info_downloaded is None:
            self.info_downloaded = ffprobe_wrap(self.downloaded,
                                                extra_args=extra_args,
                                                is_verbose=is_verbose)

        return self.info_downloaded
        

def process(spec: VideoSpec):
    ...


if __name__ == '__main__':
    testspec = {
        'url': 'https://www.youtube.com/watch?v=OgR9CnNHCc0',
        'outfile': 'IDEAS/preacher-curl.mp4',
        'builddir': 'IDEAS/videograb-tmp'
    }
    spec = VideoSpec(**testspec, is_verbose=True)
    dl, meta = spec.download()
    probed = spec.probe()