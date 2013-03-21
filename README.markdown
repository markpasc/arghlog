# arghlog #

`arghlog` is a module for integrating `argh` CLI tools with standard Python `logging`. It is an experiment derived from [`termtool`](https://github.com/markpasc/termtool).


## Usage ##

Use the `arghlog.add_logging()` function to add logging options to the argument parser. That is, instead of:

    import argh

    def foo():
        pass

    argh.dispatch_command(foo)

use:

    import argh
    import arghlog

    def foo():
        pass

    parser = argh.ArghParser()
    arghlog.add_logging(parser)
    parser.set_default_command(foo)
    parser.dispatch()

This provides the command options:

    usage: foo [-h] [-v] [-q] [--color] [--no-color]

    optional arguments:
      -h, --help  show this help message and exit
      -v          use more verbose logging (stackable)
      -q          use less verbose logging (stackable)
      --color     use color in log (when available)
      --no-color  use no color in log
