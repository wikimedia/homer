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
    parser.add_argument('query', help='Select which devices to target')

    subparsers = parser.add_subparsers(help='Action to perform: generate, diff, commit', dest='action')
    subparsers.required = True

    subparsers.add_parser('generate', help='Generate the configurations locally.')

    diff = subparsers.add_parser('diff', help=('Perform a commit check and show the differences between the generated '
                                               'configuration and the live one.'))
    diff.add_argument('-o', '--omit-diff', action='store_true',
                      help='Omit the actual diff to prevent the leak of private data')

    commit = subparsers.add_parser('commit', help='Actually commit the generated configuration to the devices.')
    commit.add_argument('message', help='A mandatory commit message. The running username will be automatically added.')

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

    kwargs = {}
    if args.action == 'commit':
        kwargs['message'] = args.message
    elif args.action == 'diff':
        kwargs['omit_diff'] = args.omit_diff

    config = load_yaml_config(args.config)
    runner = Homer(config)
    return getattr(runner, args.action)(args.query, **kwargs)


if __name__ == '__main__':
    sys.exit(main(argv=sys.argv[1:]))
