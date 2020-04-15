import json
import logging
import time
from typing import Dict, List, Literal, Union, TYPE_CHECKING, Iterator, cast

from django.contrib.staticfiles.storage import staticfiles_storage

from .exceptions import (
    WebpackError,
    WebpackLoaderBadStatsError,
    WebpackLoaderTimeoutError,
    WebpackBundleLookupError
)


if TYPE_CHECKING:
    try:
        from typing import TypedDict
    except ImportError:
        try:
            from mypy_extensions import TypedDict
        except ImportError:
            TypedDict = None

    # note if TypedDict does not exist, mypy will fail here
    if TypedDict is not None:
        from .config import WebpackConfig

        class WebpackBundleAsset(TypedDict, total=False):
            name: str
            publicPath: str
            path: str
            integrity: str
            __url__: str

        class WebpackBundleError(TypedDict, total=False):
            status: Literal["error"]
            file: str
            error: str
            message: str

        class WebpackBundleCompiling(TypedDict):
            status: Union[Literal["initialization"], Literal["compile"]]

        class WebpackBundleCompiled(TypedDict, total=False):
            status: Literal["done"]
            publicPath: str
            error: str
            message: str
            # chunks: { <bundle name> : [ chunk name, chunk name, ... ] }
            chunks: Dict[str, List[str]]
            # assets: { <chunk name> : { ... } }
            assets: Dict[str, WebpackBundleAsset]
            startTime: int
            endTime: int

        WebpackBundleContents = Union[WebpackBundleCompiled, WebpackBundleCompiling, WebpackBundleError]


logger = logging.getLogger(__name__)


class WebpackLoader(object):
    name: str
    config: "WebpackConfig"
    # Class property - used in classmethod only
    _assets: Dict[str, "WebpackBundleContents"]

    def __init__(self, name: str, config: "WebpackConfig") -> None:
        self.name = name
        self.config = config

    @classmethod
    def global_cache(cls) -> Dict[str, "WebpackBundleContents"]:
        return cls._assets

    def load_assets(self) -> "WebpackBundleContents":
        """Function to load the bundle stats. This is the main function to override in a custom loader."""

        try:
            logger.debug("Loading webpack stats file %s", self.config['STATS_FILE'])

            with open(self.config['STATS_FILE'], encoding="utf-8") as f:
                return json.load(f)
        except IOError as exc:
            raise IOError(
                f'Error reading {self.config["STATS_FILE"]}: {exc}. '
                f'Are you sure webpack has generated the file and the path is correct?'
            )

    def get_assets(self, compiled=True, replace_cache=False) -> "WebpackBundleContents":
        """Retrieves and optionally (if enabled) caches webpack bundle stats"""

        if self.config['CACHE']:
            logger.debug("Using global stats cache")
            cache = self.global_cache()

            # If replace_cache is True, bust the cache and replace it anyway
            if self.name not in cache or replace_cache:
                logger.debug("Stats for '%s' not in global cache, loading from load_assets()...")
                cache[self.name] = self.load_assets()
            else:
                logger.debug("Stats for '%s' found in global cache, using cached data...")
            assets = cache[self.name]
        else:
            logger.debug("Cache disabled, loading stats from load_assets()...")
            assets = self.load_assets()

        if compiled:
            if assets['status'] != 'done':
                # Raise error if status == error
                self.raise_error_from_stats()
                # If status != error, raise a generic error
                raise WebpackLoaderBadStatsError(
                    f'Tried to access webpack stats "{self.name}", but it has status "{assets["status"]}"'
                )
            else:
                return assets
        else:
            return assets

    def get_chunk_from_name(self, chunk_name: str) -> "WebpackBundleAsset":
        """Retrieve the chunk asset for chunk_name, from the stats data"""

        try:
            logger.debug('Retrieving asset with chunk name "%s"', chunk_name)
            return cast("WebpackBundleCompiled", self.get_assets(compiled=True)).get("assets", {})[chunk_name]
        except KeyError:
            logger.error('Could not find asset with chunk name "%s"', chunk_name)
            raise WebpackBundleLookupError(f"The asset name '{chunk_name}' could not be found.")

    def get_chunk_url(self, chunk: "WebpackBundleAsset") -> str:
        """Get URL, potentially prefixing with BUNDLE_DIR_NAME"""

        public_path = chunk.get('publicPath', None)
        if public_path is not None:
            # Just return the public path instead of the django-generated path
            return public_path

        return staticfiles_storage.url(f'{self.config["BUNDLE_DIR_NAME"]}{chunk["name"]}')

    def raise_error_from_stats(self) -> None:
        # Currently only returns the first error...
        assets = self.get_assets()

        if assets['status'] in {'initialization', 'compile'}:
            error = assets.get('error', 'Webpack has not finished compiling')
            message = 'Webpack is either not running or still compiling the bundle'
        elif assets['status'] == 'error':
            error = assets.get('error', 'Unknown Error')
            message = assets.get('message', '')
        else:
            return
        logger.error("Error found in webpack: '%s' - %s", error, message)
        raise WebpackError(f"Error in webpack '{error}': {message}")

    def get_bundle(self, bundle_name: str) -> Iterator["WebpackBundleAsset"]:
        """Get bundle based on bundle_name"""

        logger.debug('Loading bundle "%s" from loader "%s"', bundle_name, self.name)

        # If timeout is none, don't poll. If timeout is zero, poll forever.
        timeout = self.config['TIMEOUT']
        assets = self.get_assets()

        # poll and block request until bundle is compiled or the build times out
        if timeout is not None:
            logger.debug('Polling enabled, checking for completed assets file.')
            timed_out = False
            interval_time = self.config['POLL_INTERVAL']
            start_time = time.time()

            while not timed_out and assets['status'] in {'initialization', 'compile'}:
                logger.info('Assets file "%s" incomplete, polling every %f seconds', self.name, interval_time)
                time.sleep(interval_time)
                if timeout > 0 and (time.time() - timeout > start_time):
                    timed_out = True
                # Use replace_cache to make sure we load from disk each time
                assets = self.get_assets(replace_cache=True)

            if timed_out:
                logger.critical('Assets file "%s" did not finish compiling before we timed out.', self.name)
                raise WebpackLoaderTimeoutError(
                    f"Timed Out. Bundle `{bundle_name}` took more than {timeout} seconds to compile."
                )
            else:
                logger.info('Assets file "%s" finished compiled.', self.name)

        if assets['status'] == 'done':
            try:
                for chunk_name in assets['chunks'][bundle_name]:
                    chunk = self.get_chunk_from_name(chunk_name)

                    # If __url__ already exists, we don't need to re-run the regexes.
                    # This will help performance (a little) if we have caching turned on.
                    if '__url__' not in chunk and not any(regex.match(chunk_name) for regex in self.config['ignores']):
                        chunk['__url__'] = self.get_chunk_url(chunk)
                    if '__url__' in chunk:
                        yield chunk

                # Finished iteration
                return
            except KeyError:
                raise WebpackBundleLookupError(f'Cannot resolve bundle {bundle_name}.')

        # if assets['status'] == 'error', raise an exception
        self.raise_error_from_stats()

        logger.error("Error found in webpack stats data: unknown status '%s'", assets['status'])
        raise WebpackLoaderBadStatsError(
            "The stats file does not contain valid data. Make sure webpack-bundle-tracker "
            "plugin is enabled and try to run webpack again."
        )
