"""Assign initial IDs to FreeDB exercises (by renaming dirs)"""

from itertools import filterfalse
from tools.lint import Linter

def build(env, log):
    _, dirs, __ = next(env.exc_dir.walk())
    curnames = dirs

    linter = Linter()
    badnames = list(filterfalse(linter.id_lint, curnames))
    badnames.sort()

    if not badnames:
        log.warning(f'SKIPPING\t- ID dirnames lint OK')
        return
    
    log.info(f'Lint found {len(badnames)} bad exercise ID dirnames')
    log.debug('\t' + '\n\t'.join(badnames))
    log.info(f'Renaming...')

    rest = []
    nrenamed = 0
    for name in badnames:
        newname = linter.id_fixup(name)

        # apply custom renames
        newname = linter.id_fixup_rename(newname)

        if not linter.id_lint(newname):
            rest.append(newname)
        if name == newname:
            continue

        oldpth = env.exc_dir.joinpath(name)
        newpth = env.exc_dir.joinpath(newname)
        oldpth.rename(newpth)
        nrenamed += 1
    
    log.info(f'Renamed {nrenamed} idents using standard scheme')
    rest.sort()
    if rest:
        log.info(f'Rest (non-linting) [{len(rest)}]:\n\t' + '\n\t'.join(rest))
    return