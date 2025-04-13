"""Grabs videos from a remote source, cuts and processes them based on a spec.

Dependencies: yt-dlp, ffmpeg, ffprobe (part of ffmpeg)
"""

from dataclasses import dataclass, field
import json
import pathlib as pth
import shutil
import subprocess as sp
import tempfile
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

            if not isinstance(v, str):  # assume something iterable -> join it
                v = lstsep.join(v)

            if isinstance(v, str):
                col += [k, v] if kvsep is None else [k + kvsep + v]
                continue
            
            raise RuntimeError(f"Ewww, '{k}': '{v}'... What are you feeding me with?")

        return col
    
    return parse_level(dct)



class VideoSpec:
    url: str
    outfile: pth.Path
    builddir: pth.Path
    metadata: dict | None = None    # @FIXME: avoid very long output via repr
    downloaded: pth.Path | None = None

    _tmpdir: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    # Whether to overwrite files. Class-level default
    OVERWRITE: bool = False
    # Template for json filenames
    META_JSON_TPL: str = '{name}.meta.json'
    # Downloaded file name
    DOWNLOADED_TPL: str = '{name}.dl.mkv'

    FFPROBE_PATH: pth.Path = pth.Path('ffprobe')

    FFPROBE_ARGS: dict = {
        'loglevel': 'error',        # filter-out unusable data
        'print_format': 'json',     # we'll parse that
        'select_streams': 'v',      # all video streams
        'show_entries': {
            'stream': ['width', 'height', 'avg_frame_rate', 'bit_rate'],
            'format': ['bit_rate']
        }
    }

    def __init__(self, url: str, outfile: pth.Path | str,
                 builddir: pth.Path | str | None = None,
                 *, is_overwrite: bool | None = None):
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

        if is_overwrite is not None:    # otherwise use class-level default
            self.OVERWRITE = is_overwrite

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

        is_overwrite = is_overwrite if is_overwrite is not None else self.OVERWRITE
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
        is_overwrite = is_overwrite if is_overwrite is not None else self.OVERWRITE

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
    
    @classmethod
    def _ffprobe_wrap(cls, videofile: pth.Path | str):
        """A wrapper to call ffprobe and get information on the video file."""
        videofile = pth.Path(video)
        assert videofile.exists(), f'File {videofile} not found'

        # We need to use fully-qualified path to executable
        # per https://docs.python.org/3/library/subprocess.html#subprocess.Popen
        ffprobe = self.FFPROBE_PATH
        bin = shutil.which(ffprobe)
        assert bin is not None, f'ffprobe path {ffprobe} not found'


        args = [bin]
         


    def probe(self):
        """Gets the information on a downloaded file using ffprobe"""
        ...
        

def process(spec: VideoSpec):
    ...


if __name__ == '__main__':
    testspec = {
        'url': 'https://www.youtube.com/watch?v=OgR9CnNHCc0',
        'outfile': 'IDEAS/preacher-curl.mp4',
        'builddir': 'IDEAS/videograb-tmp'
    }
    spec = VideoSpec(**testspec)