import logging
from typing import Optional, List, TYPE_CHECKING

from django import template, VERSION
from django.utils.html import format_html_join, format_html

from .. import utils

if TYPE_CHECKING:
    from ..loader import WebpackBundleAsset

logger = logging.getLogger(__name__)
register = template.Library()


@register.simple_tag
def render_bundle(
        bundle_name: str, extension: Optional[str] = None, config: str = 'DEFAULT', attrs: str = ''
) -> str:
    tags = utils.get_as_tags(bundle_name, extension=extension, config=config, attrs=attrs)
    return format_html_join("\n", "{}", ((tag,) for tag in tags))


@register.simple_tag
def webpack_static(asset_name: str, config: str = 'DEFAULT') -> str:
    return format_html("{}", utils.get_static(asset_name, config=config))


@register.simple_tag
def get_files(
        bundle_name: str, extension: Optional[str] = None, config: str = 'DEFAULT'
) -> List["WebpackBundleAsset"]:
    """
    Returns all chunks in the given bundle.
    Example usage::

        {% get_files 'editor' 'css' as editor_css_chunks %}
        CKEDITOR.config.contentsCss = '{{ editor_css_chunks.0.publicPath }}';

    :param bundle_name: The name of the bundle
    :param extension: (optional) filter by extension
    :param config: (optional) the name of the configuration
    :return: a list of matching chunks
    """

    return utils.get_files(bundle_name, extension=extension, config=config)
