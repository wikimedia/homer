"""Homer's CLI."""
import argparse
import logging
import sys

from typing import Optional

from homer import Homer
from homer.config import load_yaml_config


def argument_parser() -> argparse.ArgumentParser:
    """Get the CLI argument parser.

    Returns:
        argparse.ArgumentParser: the argument parser instance.

    """
    parser = argparse.ArgumentParser(description="Configuration manager for network devices")
    parser.set_defaults(loglevel=logging.INFO)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-v', '--verbose', action='store_const', const=logging.DEBUG, dest='loglevel',
                       help='Verbose (debug) logging')
    group.add_argument('-q', '--quiet', action='store_const', const=logging.WARN, dest='loglevel',
                       help='Silent mode, only log warnings',)
    parser.add_argument('-c', '--config', default='/etc/homer/config.yaml', help='Main configuration file to load.')
    parser.add_argument('action', choices=('generate', 'diff'),
                        help=('Select which action to perform. Use generate to just generate the configurations '
                              'locally, diff to perform a commit check on the target devices and commit to apply the '
                              'configuration to the target devices.'))
    parser.add_argument('query', help='Select which devices to target')

    return parser


def main(argv: Optional[list] = None) -> int:
    """Run the Homer CLI.

    Arguments:
        argv (list): the command line arguments to parse.

    Returns:
        int: ``0`` on success, ``1`` on failure.

    """
    args = argument_parser().parse_args(argv)
    logging.basicConfig(level=args.loglevel)
    if args.loglevel != logging.DEBUG:  # Suppress noisy loggers
        logging.getLogger('ncclient').setLevel(logging.WARNING)
    config = load_yaml_config(args.config)
    runner = Homer(config)
    return getattr(runner, args.action)(args.query)


if __name__ == '__main__':
    sys.exit(main(argv=sys.argv[1:]))
