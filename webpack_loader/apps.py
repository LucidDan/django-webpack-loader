from typing import List, Optional
import re

from django.apps import AppConfig
from django.core.checks import register, Tags, Error
from django.utils.module_loading import import_string


@register(Tags.compatibility)
def webpack_valid_config_check(app_configs: Optional[List[str]] = None,  **kwargs) -> List[Error]:
    """Run django checks to determine if the config is valid or not"""

    def make_error(err_str, err_code):
        return Error(
            'Error while parsing WEBPACK_LOADER configuration',
            hint=err_str,
            obj='django.conf.settings.WEBPACK_LOADER',
            id=f'django-webpack-loader.{err_code}'
        )

    errors: List[Error] = []

    try:
        # Load locally since we want to give django a chance to initialize first
        from webpack_loader.config import get_all_configs
        configs = get_all_configs()

        if 'DEFAULT' not in configs:
            errors.append(make_error('Missing DEFAULT configuration', 'E002'))
        for name, config in configs.items():
            try:
                module = import_string(config['LOADER_CLASS'])
            except ImportError as exc:
                errors.append(make_error(f'Could not import LOADER_CLASS "{config["LOADER_CLASS"]}"', 'E003'))

        # FIXME: check types (CACHE is bool, TIMEOUT is int, etc)
    except (TypeError, IndexError, ValueError, re.error) as exc:
        errors.append(make_error(f'Got exception: {exc}', 'E001'))

    return errors


class WebpackLoaderConfig(AppConfig):
    name = 'webpack_loader'
    verbose_name = "Webpack Loader"
