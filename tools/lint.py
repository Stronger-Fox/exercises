"""Linting tools for exercises"""

import string
from typing import Optional

class Linter:
    id_max_len = 40          # 95% of original freedb names are <= 40 symbols
    ID_ALLOWED_SYMS = set(string.ascii_lowercase + string.digits + '_')

    def __init__(self, *, 
                 id_max_len: Optional[int] = None):
        if id_max_len is not None:
            self.id_max_len = id_max_len

    def id_lint(self, id: str) -> bool:
        """Checks whether exercise identifier is correctly named."""
        if len(id) > self.id_max_len:
            return False
        if set(id) - self.ID_ALLOWED_SYMS:
            return False
        return True

    @staticmethod
    def id_fixup(id: str) -> str:
        # '-' may be unacceptable in further uses elsewhere
        id = id.replace('-', '_')
        id = id.lower()

        while '__' in id:
            id = id.replace('__', '_')

        return id
    
    @staticmethod
    def id_fixup_rename(oldid: str) -> str:
        replacements = {
            'one_arm': '1arm',
            'two_arm': '2arm',
            'triceps': 'tricep',
            'biceps': 'bicep',
            'lateral': 'lat',
            # 'barbell': 'bbell',
            # 'dumbbell': 'dbell',
            # 'kettlebell': 'kbell',
            'smith_machine': 'smith',
            # 'bent_over': 'bover',
            # 'extended': 'ext',
            # 'extension': 'ext',
            # 'decline': 'decl',
            # 'incline': 'incl',
            # 'alternating': 'alt',
            # 'isometric': 'iso',
            # 'close_grip': 'cgrip',
            # 'wide_grip': 'wgrip',
            # 'reverse': 'rev',
            # 'standing': 'std',
            'v_bar': 'vbar'
        }

        name = oldid
        for k, v in replacements.items():
            name = name.replace(k, v)
        return name