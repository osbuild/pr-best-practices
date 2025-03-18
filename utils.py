import pickle
import os
import re

from typing import Any
from collections.abc import Mapping, Callable

def format_help_as_md(parser):
    help_text = parser.format_help()
    section = re.compile("^(.+):$")
    ret = []
    in_block = False
    for line in help_text.split("\n"):
        m = section.match(line)
        if line.startswith("usage:"):
            ret.append(line.replace("usage:", "# Usage\n```\n" + " "*6))
            in_block = True
        elif m:
            ret.append(line.replace(m.group(0), f"# {m.group(1).capitalize()}\n```"))
            in_block = True
        elif in_block and len(line) == 0:
            ret.append("```")
            in_block = False
        else:
            ret.append(line)
    return "\n".join(ret)

class Cache:
    def __init__(self, cache_file: str|None = None):
        self.cache_file = cache_file
        self.cache = {}
        self.cache_on = cache_file is not None

        if self.cache_on:
            self._cache_load(cache_file)

    def _cache_load(self, cache_file: str) -> None:
        """
        Load the cache file.
        """
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "rb") as f:
                self.cache = pickle.load(f)


    def _cache_save(self) -> None:
        """
        Save the cache file.
        """
        with open(self.cache_file, "wb") as f:
            pickle.dump(self.cache, f)


    def cached_result(self, cache_key: str, function: Callable, **kwargs) -> tuple[Any, Mapping[str, Any]]:
        """
        Cache the result of a function call.
        Only to be used for local testing!
        """
        if self.cache_on:
            result = self.cache.get(cache_key)
        else:
            result = None
        if result is None:
            result = function(**kwargs)
            if self.cache_on:
                self.cache[cache_key] = result
                # better save now, so it's not lost if the script crashes
                self._cache_save()

        return result