import logging
import os
import os.path
import re
import sys

import argparse


__version__ = '0.9'


LOG_FORMAT = '%(levelcolor)s%(levelname)s%(resetcolor)s %(message)s'
"""The default logging format string that `add_logging()` will configure logging with."""

LOG_LEVEL = logging.WARN
"""The default logging level that `add_logging()` will configure logging with."""

STRIP_COLOR = re.compile(r'\033\[[^m]+m')
"""The compiled regular expression to remove ANSI color codes from a string."""


class _LogLevelAddAction(argparse.Action):

    """An `argparse` action for selecting a `logging` level."""

    LEVELS = (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)

    def __init__(self, option_strings, dest, const, default=None, required=False, help=None, metavar=None):
        # Log level addition actions take no arguments.
        super(_LogLevelAddAction, self).__init__(nargs=0,
            option_strings=option_strings, dest=dest, const=const,
            default=default, required=required, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        level = getattr(namespace, self.dest, logging.WARNING)
        index = self.LEVELS.index(level)
        addend = self.const if self.const is not None else 1
        try:
            level = self.LEVELS[index + addend]
        except IndexError:
            pass
        else:
            setattr(namespace, self.dest, level)

            # We don't really get a chance to set the level later so set it now.
            logging.getLogger().setLevel(level)


class _NoColorLogFormatter(logging.Formatter):

    def format(self, record):
        record.levelcolor = ''
        record.resetcolor = ''
        logline = super(_NoColorLogFormatter, self).format(record)
        return STRIP_COLOR.sub('', logline)


class _ColorLogFormatter(logging.Formatter):

    color_for_level = {
        logging.DEBUG:    '32',  # green
        logging.INFO:     '37',  # white
        logging.WARNING:  '33',  # yellow
        logging.ERROR:    '31',  # red
        logging.CRITICAL: '35',  # magenta
    }

    def format(self, record):
        color = self.color_for_level.get(record.levelno)
        if color is not None:
            record.levelcolor = u'\033[1;%sm' % color
        record.resetcolor = u'\033[0m'
        return super(_ColorLogFormatter, self).format(record)


def add_logging(parser, log_format=LOG_FORMAT, log_level=LOG_LEVEL, color=True):
    """Configures the `argparse.ArgumentParser` with arguments to configure
    logging.

    This adds arguments:

    * ``-v`` to increase the log level
    * ``-q`` to decrease the log level
    * ``--color`` to enable color logging when available
    * ``--no-color`` to disable color logging

    The root logger is configured with the given format and log level. ANSI
    color codes are supported in the logging format string. If color is enabled
    and stderr is a tty, the codes will be passed through. Otherwise the
    logging formatter will strip them out. The logging format supports these
    additional format variables for coloration:

    %(levelcolor)s    If stderr is a terminal, an ANSI color code
                      appropriate for the level of the logged record.
    %(resetcolor)s    If stderr is a terminal, an ANSI color reset code.

    """
    parser.set_defaults(log_level=log_level)
    parser.add_argument('-v', dest='log_level', action=_LogLevelAddAction, const=1, help='use more verbose logging (stackable)')
    parser.add_argument('-q', dest='log_level', action=_LogLevelAddAction, const=-1, help='use less verbose logging (stackable)')

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler()  # using sys.stderr
    if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():

        class ColorAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                setattr(namespace, self.dest, True)
                handler.setFormatter(_ColorLogFormatter(log_format))

        class NoColorAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                setattr(namespace, self.dest, False)
                handler.setFormatter(_NoColorLogFormatter(log_format))

        parser.add_argument('--color', dest='color', action=ColorAction, nargs=0, help='use color in log (when available)')
        parser.add_argument('--no-color', dest='color', action=NoColorAction, nargs=0, help='use no color in log')

        if color:
            formatter_class = _ColorLogFormatter
        else:
            formatter_class = _NoColorLogFormatter
    else:
        # Make the options available, but they don't do anything.
        parser.add_argument('--color', dest='color', action='store_true', help='use color in log (when available)')
        parser.add_argument('--no-color', dest='color', action='store_false', help='use no color in log')
        formatter_class = _NoColorLogFormatter

    handler.setFormatter(formatter_class(log_format))
    root_logger.addHandler(handler)
