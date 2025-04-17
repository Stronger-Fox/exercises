"""This module contains common data structures to be used in project."""

from collections.abc import MutableMapping
import typing

class IDMap(MutableMapping):
    """Class provides a mapping for the collection of objects,
    identified using their attribute.
    
    Mapping takes form of obj.attr: obj. Where attr is passed
    during instance creation.
    """
    lookup: dict[str, typing.Any]

    def __init__(self, attr: str, /, *args, **kwargs):
        self.attr = attr
        self.lookup = dict(*args, **kwargs)
        self.rebuild()

    def __get_key__(self, value, /):
        return str(getattr(value, self.attr))
    
    def rebuild(self):
        l = {self.__get_key__(obj): obj for obj in self.lookup.values()}
        self.lookup = l
    
    def add_item(self, value, /):
        self.lookup[self.__get_key__(value)] = value
    
    def remove_item(self, value, /):
        del self.lookup[self.__get_key__(value)]
        
    def __getitem__(self, key, /):
        try:
            return self.lookup[key]
        except KeyError:
            pass

        self.rebuild()
        return self.lookup[key]

    def __setitem__(self, key, value, /):
        self.lookup[key] = value
        self.rebuild()
        return value

    def __delitem__(self, key, /):
        try:
            del self.lookup[key]
        except KeyError:
            pass
        
        self.rebuild()
        del self.lookup[key]

    def __iter__(self):
        self.rebuild()
        return iter(self.lookup)

    def __len__(self):
        return len(self.lookup)
    
    def __repr__(self):
        cls = type(self).__name__
        inner = repr(self.lookup)
        fld = f'attr={self.attr!r}'
        return f'{cls}({fld}, {inner})'

# now unused, maybe will find its use somewhere later
class TeeIOWriter:
    """Tees writes across different io buffers.

    All other attribute lookups are passed to main writer
    """

    def __init__(self, main, *others):
        self.main = main
        self.writers = (main, ) + others

    def write(self, data):
        for writer in self.writers:
            writer.write(data)

    def flush(self):
        for writer in self.writers:
            writer.flush()
    
    def close(self):
        for writer in self.writers:
            writer.close()
    
    def __getattr__(self, attr):
        return self.main.__getattr__(attr)
    
    # have to provide these as well, as they're always looked at class-level
    def __iter__(self):
        return self.main.__iter__()
    
    def __next__(self):
        return self.main.__next__()
    
    def __enter__(self):
        return self.main.__enter__()
    
    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        return self.main.__exit__(exc_type, exc_value, traceback)