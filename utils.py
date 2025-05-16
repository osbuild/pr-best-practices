import logging
import pickle
import os
import re
import threading

from typing import Any
from collections.abc import Mapping, Callable

import yaml

logger = logging.getLogger(__name__)

def format_help_as_md(parser):
    help_text = parser.format_help()
    section = re.compile(r"^([\w ]+):$")
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

        # two locks to avoid race conditions when accessing the cache
        # but also being able to run independent operations in parallel
        self._cache_lock = threading.Lock()
        self._cache_per_key_lock = {}

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

        This function is thread safe having `function()` run in parallel but only for
        distinct `cache_key` values.
        """
        cache_key_lock = None
        if self.cache_on:
            with self._cache_lock:
                cache_key_lock = self._cache_per_key_lock.get(cache_key)
                if not cache_key_lock:
                    cache_key_lock = threading.Lock()
                    self._cache_per_key_lock[cache_key] = cache_key_lock
            cache_key_lock.acquire()
            with self._cache_lock:
                result = self.cache.get(cache_key)
        else:
            result = None
        # catch all exceptions as we need to release the lock
        try:
            if result is None:
                result = function(**kwargs)
                if self.cache_on:
                    with self._cache_lock:
                        self.cache[cache_key] = result
                        # better save now, so it's not lost if the script crashes
                        self._cache_save()
        except:
            raise
        finally:
            if cache_key_lock:
                cache_key_lock.release()

        return result

class UserMap:
    """
    A class to map user IDs between tools.
    This class is not runtime optimized as it is only used for a few lookups.
    """

    def __init__(self, user_map_file: str):
        try:
            with open(user_map_file, 'r') as yaml_file:
                self.user_map = yaml.safe_load(yaml_file)['assignees']
                # consistency check
                for entry in self.user_map:
                    if not entry.get('github'):
                        raise ValueError(f"Missing 'github' key in entry: {entry}")
                    if not entry.get('jira'):
                        raise ValueError(f"Missing 'jira' key in entry: {entry}")
                    # slack can be missing
        except Exception as e:
            logging.error(f"Error loading YAML file '{user_map_file}': {e}")
            raise e

    def _get_value(self, entry: dict, tool: str) -> Any:
        """
        Get the entry for a user from the user map.
        """
        ret = entry.get(tool)
        if not ret and tool == 'slack':
            # slack can be derived from jira
            # remove the "@" and domain if present at the end
            ret = entry.get('jira')
            if ret:
                ret = re.sub(r'@.*$', '', ret)
        return ret

    def _get_user(self, user_name: str, from_tool: str, to_tool: str) -> str:
        for entry in self.user_map:
            if self._get_value(entry, from_tool) == user_name:
                ret = self._get_value(entry, to_tool)
                return ret
        return None

    def jira2github(self, user_name: str) -> str:
        return self._get_user(user_name, 'jira', 'github')
    def jira2slack(self, user_name: str) -> str:
        return self._get_user(user_name, 'jira', 'slack')

    def github2jira(self, user_name: str) -> str:
        return self._get_user(user_name, 'github', 'jira')
    def github2slack(self, user_name: str) -> str:
        return self._get_user(user_name, 'github', 'slack')

    def slack2jira(self, user_name: str) -> str:
        return self._get_user(user_name, 'slack', 'jira')
    def slack2github(self, user_name: str) -> str:
        return self._get_user(user_name, 'slack', 'github')
