#!/usr/bin/env python3
import sys
import typing as ty
import csv
from pathlib import Path
import itertools
import argparse
import readline
import dataclasses

import numpy as np
import tomli

if sys.platform == 'win32':
    try:
        import colorama
        colorama.just_fix_windows_console()
        use_color = True
    except ImportError:
        use_color = False
else:
    use_color = True


def make_parser():
    parser = argparse.ArgumentParser(
        description=('Vocabulary notebook sampler.  '
                     'The vocabulary notebook should be a tab-separated '
                     'values (TSV) file. It should at the first line include '
                     'a header line, and as columns contain at least these '
                     'fields: a familiarity score, the word, the meaning, '
                     'and some examples. The familiarity scores are integers '
                     'ranging from 1 to 5, with 1 being the most unfamiliar '
                     'words. Multiple examples may be separated by " // " in '
                     'a TSV cell. If there\'s no example, leave that cell '
                     'empty.'))
    parser.add_argument(
        '-T',
        '--total',
        type=int,
        help='total number of words to sample')
    parser.add_argument(
        '-m',
        '--min',
        help='min number of non-5 familiarity scored words to sample')
    parser.add_argument(
        '-P',
        '--pronounce',
        action='store_true',
        help=('to pronounce aloud every sampled word as long as '
              'there\'s a pronunciation for it; note that this will slow '
              'down the initialization of the app'))
    parser.add_argument(
        '--csvformat',
        metavar='COL_ID,COL_NAME:...',
        help=('specify which field can be found at which column id (0-based), '
              'where the field names are: (F)amiliarity, (W)ord, (M)eaning, '
              'and (E)xample [e.g.: "0,F:1,W:2,M:4,E"] [default: the one '
              'specified in `~/.config/vocabnb/config.toml`]'))
    parser.add_argument(
        '-f',
        '--nbfile',
        type=Path,
        help='the path to the vocabulary notebook file')
    parser.add_argument(
        '-C',
        '--cachedir',
        help=('if specified neither here nor in the configuration file, '
              'no cache will be made'))
    parser.add_argument(
        '-c',
        '--configfile',
        type=Path,
        help=('use CONFIGFILE as the configuration file rather than '
              '`~/.config/vocabnb/config.toml`'))
    return parser


def sample_vocab(
    fam,
    max_total_vocab: int,
    min_non5_vocab: int,
) -> ty.List[int]:
    """
    Sample words according to familiarity scores.

    Sampling rule:

        - Words with score=5 must be sampled, but the order should be shuffled.
          Suppose there are N5 number of such words. Suppose also that there
          are N words in total.
        - For the remaining min(N - N5, max(``max_total_vocab`` - N5,
          ``min_non5_vocab``)) words, sample without replacement, where the
          sampling weights are exp(familiarity scores <=4)

    :param fam: the familiarity scores of the vocabulary, int array
    :param max_total_vocab: max number of words to sample
    :param min_non5_vocab: min number of non-5 scored words to sample, which
           takes precedence over ``max_total_vocab``
    :return: list of word indices
    """
    fam = np.copy(fam)
    N = fam.shape[0]
    j5 = np.nonzero(fam == 5)[0]
    N5 = j5.shape[0]
    n_non5_samples = min(N - N5, max(max_total_vocab - N5, min_non5_vocab))
    fam[j5] = -999999999  # so that j5 words will not be repeatedly sampled
    # See https://timvieira.github.io/blog/post/2019/09/16/algorithms-for-sampling-without-replacement/
    G = np.random.gumbel(0, 1, size=N)
    G += fam.astype(float)
    G *= -1
    jnon5 = np.argsort(G)[:n_non5_samples]
    j = np.concatenate((j5, jnon5))
    np.random.shuffle(j)
    return j.tolist()


@dataclasses.dataclass(init=False, eq=False)
class Config:
    total: int = None
    min: int = None
    pronounce: bool = None
    csvformat: str = None
    nbfile: Path = None
    cachedir: Path = None


def read_config(args: argparse.Namespace):
    if args.configfile:
        filename = args.configfile
    else:
        filename = Path('~/.config/vocabnb/config.toml').expanduser()
    with open(filename, 'rb') as infile:
        cfgfile = tomli.load(infile)
    cfg = Config()
    for field in dataclasses.fields(Config):
        if field.name in cfgfile:
            setattr(cfg, field.name, cfgfile[field.name])
        cmd_value = getattr(args, field.name) is not None
        if cmd_value:
            setattr(cfg, field.name, cmd_value)
    if cfg.nbfile is not None:
        cfg.nbfile = Path(cfg.nbfile).expanduser()
    if cfg.cachedir is not None:
        cfg.cachedir = Path(cfg.cachedir).expanduser()
    return cfg
