from setuptools import setup
import sys

install_requires = ['numpy', 'tomli']
extra_requires_color = []
if sys.platform == 'win32':
    extra_requires_color.append('colorama')
extra_requires_init_progress = ['tqdm']
extra_requires_pronounce = ['requests']
if sys.platform != 'darwin':
    extra_requires_pronounce.append('fake-useragent')

setup(
    name='vocabnb',
    py_modules=['vocabnb'],
    version='0.3.1',
    install_requires=install_requires,
    extras_require={
        'color': extra_requires_color,
        'init-progress': extra_requires_init_progress,
        'pronounce': extra_requires_pronounce,
    },
    entry_points={
        'console_scripts': [
            'vocabnb = vocabnb:main',
        ],
    },
)
