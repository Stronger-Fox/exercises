"""Apply changes from freedb_patch.yml to FreeDB dataset"""

import pathlib as pth
from ruamel.yaml import YAML as _YAML
yaml=_YAML(typ='safe')

PATCH_FILE = 'freedb_patch.yml'

SCRIPT_ROOT = pth.Path(__file__).parent
PATCH_FILE = SCRIPT_ROOT.joinpath(PATCH_FILE)

def build(env, log):
    exercises = env.freedb_collection

    patches = yaml.load(PATCH_FILE)

    for name, exc in exercises.items():
        patch = patches.get(name, {})
        if patch:
            log.info(f'Patching {name}')
        
        for k, v in patch.items():
            setattr(exc, k, v)
            log.info(f'  set {k}={v}')

        if 'id' in patch:
            exc.rename(patch['id'])
            log.info(f'  Changed id: {name} -> {patch["id"]}')

        # now write it all into json for persistence
        json_file = exc.path.joinpath(env.freedb_exc_json)
        json = exc.model_dump_json(indent=2)
        with open(json_file, 'w') as file:
            file.write(json)

        relname = json_file.relative_to(json_file.parent.parent)
        log.debug(f'  Written {relname}')