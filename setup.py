from pathlib import Path
from urllib.parse import quote

from setuptools import setup


def read_requirements(name='default'):
    with (Path('requirements') / f'{name}.txt').open(encoding='utf-8') as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith('#')
        ]


def get_pronounce_dep_helper():
    path = quote(str(Path(__file__).parent / 'pronounce_dep_helper'))
    return [f'pronounce_dep_helper @ file://{path}']


setup(
    name='vocabnb',
    packages=['vocabnb'],
    version='0.4.0',
    python_requires='>=3.9',
    install_requires=read_requirements(),
    extras_require={
        'dev': read_requirements('dev'),
        'pronounce':
        read_requirements('pronounce') + get_pronounce_dep_helper(),
    },
    entry_points={
        'console_scripts': [
            'vocabnb = vocabnb.vocabnb:main',
        ],
    },
)
