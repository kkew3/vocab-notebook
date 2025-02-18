"""
The whole purpose of this dummy package is to raise an error that interrupts
the installation process if the required system dependency, i.e. either mpg123
is installed or the OS is macOS, is not met.
"""

import shutil
import sys

from setuptools import setup


class PronounceDependencyError(Exception):
    def __init__(self):
        super().__init__(
            'To pronounce aloud, either have `mpg123` installed, or run on '
            'macOS where `QuickTime Player` is avalable.')


if not (shutil.which('mpg123') or sys.platform == 'darwin'):
    raise PronounceDependencyError

setup(
    name='pronounce_dep_helper',
    description=(
        'Helper package for managing dependencies for `pronounce` feature'),
    version='0.1.0',
    py_modules=['pronounce_activated'],
)
