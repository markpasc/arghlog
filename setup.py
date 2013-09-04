from distutils.core import setup


setup(
    name='arghlog',
    version='0.9',
    description='Logging integration for argh commands',
    author='Mark Paschal',
    author_email='markpasc@markpasc.org',
    url='https://github.com/markpasc/arghlog',

    packages=[],
    py_modules=['arghlog'],
    requires=['argparse', 'argh'],
)
