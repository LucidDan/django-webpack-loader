import logging
from typing import List, Optional, Iterator, TYPE_CHECKING

from django.conf import settings
from django.utils.html import format_html
from django.utils.module_loading import import_string
from django.utils.safestring import SafeData

from .config import load_config
from .loader import WebpackLoader

if TYPE_CHECKING:
    from .loader import WebpackBundleAsset

logger = logging.getLogger(__name__)
LOADERS = {}


def get_loader(config_name: str) -> WebpackLoader:
    """Look up the webpack loader and import the module"""

    if config_name not in LOADERS:
        config = load_config(config_name)
        loader_class = import_string(config['LOADER_CLASS'])
        LOADERS[config_name] = loader_class(config_name, config)
    return LOADERS[config_name]


def _get_bundle(bundle_name: str, extension: Optional[str], config: str) -> Iterator["WebpackBundleAsset"]:
    """Internal function to generate chunks for this bundle"""

    bundle = get_loader(config).get_bundle(bundle_name)

    if extension is not None:
        # Prefix a '.' onto it
        ext = '.' + extension

        return filter(lambda chunk: chunk['name'].endswith(ext), bundle)
    else:
        return bundle


def get_files(bundle_name: str, extension: Optional[str] = None, config: str = 'DEFAULT') -> List["WebpackBundleAsset"]:
    """Returns list of chunks from named bundle"""

    return list(_get_bundle(bundle_name, extension, config))


def get_as_tags(
        bundle_name: str, extension: Optional[str] = None, config: str = 'DEFAULT', attrs: str = ''
) -> Iterator[SafeData]:
    """
    Get a list of formatted <script> & <link> tags for the assets in the
    named bundle.

    :param bundle_name: The name of the bundle
    :param extension: (optional) filter by extension, eg. 'js' or 'css'
    :param config: (optional) the name of the configuration
    :param attrs: (optional) attributes to add to the script tag
    :return: a list of formatted tags as strings
    """

    for chunk in _get_bundle(bundle_name, extension, config):
        if chunk['name'].endswith(('.js', '.js.gz')):
            yield format_html('<script type="text/javascript" src="{}" {}></script>', chunk['__url__'], attrs)
        elif chunk['name'].endswith(('.css', '.css.gz')):
            yield format_html('<link type="text/css" href="{0}" rel="stylesheet" {1}/>', chunk['__url__'], attrs)


def get_static(asset_name, config='DEFAULT'):
    """
    Equivalent to Django's 'static' look up but for webpack assets.

    :param asset_name: the name of the asset
    :param config: (optional) the name of the configuration
    :return: path to webpack asset as a string
    """

    return get_loader(config).get_assets().get('publicPath', settings.STATIC_URL) + asset_name
