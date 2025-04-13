"""Grabs videos from a remote source, cuts and processes them based on a spec."""

from dataclasses import dataclass, field
import json
import pathlib as pth
import tempfile
from yt_dlp import YoutubeDL as YDL

TOOL_NAME = pth.Path(__file__).stem

@dataclass
class VideoSpec:
    url: str
    outfile: pth.Path
    builddir: pth.Path
    metadata: dict | None = None    # @FIXME: avoid very long output via repr
    downloaded: pth.Path | None = None

    _tmpdir: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    # Whether to overwrite files. Class-level default
    OVERWRITE: bool = field(default=False, repr=False)
    # Template for json filenames
    META_JSON_TPL: str = field(default='{name}.meta.json', repr=False)
    # Downloaded file name
    DOWNLOADED_TPL: str = field(default='{name}.dl.mkv', repr=False)

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
        

def process(spec: VideoSpec):
    ...


if __name__ == '__main__':
    testspec = {
        'url': 'https://www.youtube.com/watch?v=OgR9CnNHCc0',
        'outfile': 'IDEAS/preacher-curl.mp4',
        'builddir': 'IDEAS/videograb-tmp'
    }
    spec = VideoSpec(**testspec)