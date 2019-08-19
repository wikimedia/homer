"""Homer package."""
import logging

from pkg_resources import DistributionNotFound, get_distribution

from homer.config import HierarchicalConfig


try:
    __version__ = get_distribution('homer').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Homer package."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def execute(config: dict, action: str, query: str) -> None:
    """Execute Homer based on the given configuration, action and query."""
    logger.debug('Initialized with configuration: %s', config)
    logger.info('Executing %s on %s', action, query)

    public_config = HierarchicalConfig(config['base_paths']['public'])
    private_config = HierarchicalConfig(config['base_paths'].get('private', ''))  # Optional
    print(public_config)
    print(private_config)
