#!/usr/bin/env python3
import os
import sys
import typing as ty
import csv
from pathlib import Path
import argparse
import readline
import dataclasses
from urllib import parse
import subprocess

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

try:
    import requests
    use_requests = True
except ImportError:
    use_requests = False

try:
    from fake_useragent import UserAgent
except ImportError:

    class UserAgent:
        # Safari header named as 'chrome' ...
        chrome = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) '
                  'Gecko/20100101 Firefox/109.0')


try:
    from tqdm import tqdm
except ImportError:

    def tqdm(it: ty.Iterable, *_args, **_kwargs):
        return it


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
        '-T', '--total', type=int, help='total number of words to sample')
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
        '--mwapi',
        metavar='API_KEY',
        help='the Merriam-Webster API key for pronouncing aloud')
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
    mwapi: str = None


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
        cmd_value = getattr(args, field.name)
        if cmd_value is not None:
            setattr(cfg, field.name, cmd_value)
    if cfg.nbfile is not None:
        cfg.nbfile = Path(cfg.nbfile).expanduser()
    if cfg.cachedir is not None:
        cfg.cachedir = Path(cfg.cachedir).expanduser()
    return cfg


def parse_csvformat(csvformat: str):
    name2ids = {}
    for token in csvformat.split(':'):
        col_id, _, col_name = token.partition(',')
        col_id = int(col_id)
        name2ids[col_name] = col_id
    if set('FWME') != set(name2ids):
        raise ValueError('all and only four F,W,M,E fields must be specified')
    return name2ids


class VocabBook:
    def __init__(self, nbfile: Path, colname2ids: ty.Dict[str, int]):
        self._data = []
        self.colname2ids = colname2ids
        self.nbfile = nbfile
        self.modified = False

    def __enter__(self):
        with open(self.nbfile, encoding='utf-8', newline='') as infile:
            reader = csv.reader(infile, delimiter='\t')
            for row in reader:
                self._data.append(list(row))
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Write back if modified."""
        if not self.modified:
            return
        with open(self.nbfile, 'w', encoding='utf-8', newline='') as outfile:
            writer = csv.writer(outfile, delimiter='\t')
            writer.writerows(self._data)

    def __getitem__(
        self,
        item: ty.Union[ty.Tuple[ty.Literal['F', 'W', 'M', 'E'], int],
                       ty.Literal['F']],
    ) -> ty.Union[np.ndarray, int, ty.List[str], str]:
        """
        Examples:

            vocab_book['F', 0]        -- get the first familiarity as int
            vocab_book['W', 1]        -- get the second word
            vocab_book['E', 3]        -- get the fourth list of examples
            vocab_book['F']           -- get an int array of familiarities
        """
        if item == 'F':
            j = self.colname2ids['F']
            fam = [int(row[j]) for row in self._data[1:]]
            return np.array(fam)
        col_name, i = item
        i += 1  # taking the header row into account
        j = self.colname2ids[col_name]
        value = self._data[i][j]
        if col_name == 'F':
            value = int(value)
        elif col_name == 'E':
            value = list(filter(None, (x.strip() for x in value.split('//'))))
        return value

    def __setitem__(self, key, value):
        """
        Set the ``key``-th familiarity to ``value``, where ``value`` must be
        convertible to an int.

        Examples:

            vocab_book[2] = 3       -- set the third word's familiarity to 3
        """
        j = self.colname2ids['F']
        i = key + 1  # taking the header row into account
        value = str(int(value))
        self._data[i][j] = value
        self.modified = True


if use_color:

    class Colors:
        BOLD_GREEN = '\033[1;32m'
        BOLD_CYAN = '\033[1;36m'
        BOLD_RED = '\033[1;31m'
        RESET = '\033[0m'
else:

    class Colors:
        BOLD_GREEN = ''
        BOLD_CYAN = ''
        BOLD_RED = ''
        RESET = ''


def validate_filename(name: str) -> str:
    tr = {':': '_', '/': '_', '\\': '_', '"': '_'}
    for old, new in tr.items():
        name = name.replace(old, new)
    return name


def parse_audio_url(name: str) -> str:
    """
    Parse audio basename as URL according to
    https://dictionaryapi.com/products/json#sec-2.prs .

    :param name: the audio basename
    :return: the audio URL
    """
    if name.startswith('bix'):
        subdir = 'bix'
    elif name.startswith('gg'):
        subdir = 'gg'
    elif name[0].isdigit():
        subdir = 'number'
    elif name[0] in '_':  # may not be complete
        subdir = 'number'
    else:
        subdir = name[0]
    return (f'https://media.merriam-webster.com/audio/prons/en/us/mp3/'
            f'{subdir}/{name}.mp3')


def load_pronunciation(
    book: VocabBook,
    word_indices: ty.List[int],
    api_key: str,
    cachedir: Path,
) -> ty.Dict[int, Path]:
    """
    Prerequisites:

        - ``use_requests`` is ``True``
        - ``cachedir`` is not ``None``
        - ``sys.platform`` is ``darwin``

    Returns a dictionary mapping word index to path to the audio file path.
    """
    cachedir.mkdir(parents=True, exist_ok=True)
    loaded = {}
    proxies = {}
    if 'http_proxy' in os.environ:
        proxies['http_proxy'] = os.environ['http_proxy']
    if 'https_proxy' in os.environ:
        proxies['https_proxy'] = os.environ['https_proxy']
    for j in tqdm(word_indices, desc='init'):
        word = book['W', j]
        word_file = validate_filename(word)
        cachefile = cachedir / (word_file + '.mp3')
        if cachefile.is_file():
            loaded[j] = cachefile
            continue

        word_url = (
            'https://dictionaryapi.com/api/v3/references/collegiate/json/'
            + parse.quote(word))
        ua = UserAgent()
        try:
            resp = (
                requests.get(
                    word_url,
                    params={
                        'key': api_key,
                    },
                    headers={
                        'user-agent': ua.chrome,
                    },
                    timeout=10,
                    proxies=proxies).json())
            prs_url = None
            for item in resp:
                hw = item['hwi']['hw'].replace('*', '')
                if hw == word:
                    try:
                        prs_url = parse_audio_url(
                            item['hwi']['prs'][0]['sound']['audio'])
                    except (KeyError, IndexError):
                        pass
            if not prs_url:
                continue

            content = (
                requests.get(
                    prs_url,
                    headers={
                        'user-agent': ua.chrome,
                    },
                    timeout=10,
                    proxies=proxies).content)
            with open(cachefile, 'wb') as outfile:
                outfile.write(content)
            loaded[j] = cachefile
        except (requests.exceptions.RequestException, TypeError):
            tqdm.write(f'Failed to load pronunciation for word {word}')
    return loaded


def play_audio_file(audio_path: Path):
    """Play audio file using QuickTime Player."""
    args = [
        'osascript',
        '-e',
        f'set theFile to POSIX FILE "{audio_path}"',
        '-e',
        'tell application "QuickTime Player"',
        '-e',
        'set theAudio to open file theFile',
        '-e',
        'tell theAudio',
        '-e',
        'set theDuration to duration',
        '-e',
        'play',
        '-e',
        'end tell',
        '-e',
        'delay theDuration + 1',
        '-e',
        'close theAudio',
        '-e',
        'quit',
        '-e',
        'end tell',
    ]
    try:
        subprocess.run(args, check=True, timeout=7)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass


def qa_interface(
    book: VocabBook,
    j: int,
    i: int,
    T: int,
    prs: ty.Dict[int, Path],
) -> bool:
    """
    Construct the Q&A interface for the j-th word in the vocabulary notebook.

    :param book: the vocabulary notebook
    :param j: the word index
    :param i: the question index (1-based)
    :param T: the total number of questions
    :param prs: pronunciation dict mapping a word index to the pronunciation
           audio path if exists
    :return: ``True`` if the user is familiar with current word
    """
    word = book['W', j]
    if j in prs:
        player_emoji = '🔈'
    else:
        player_emoji = ''
    print(f'{Colors.BOLD_GREEN}->{Colors.RESET} {word} '
          f'{Colors.BOLD_GREEN}[{i}/{T}]{Colors.RESET} {player_emoji}')
    if j in prs:
        play_audio_file(prs[j])
    _ = input('[any key] ')
    meaning = book['M', j]
    examples = book['E', j]
    print(f'{Colors.BOLD_CYAN}Meaning ->{Colors.RESET} {meaning}')
    for k, e in enumerate(examples, 1):
        print(f'{Colors.BOLD_CYAN}Example #{k} ->{Colors.RESET} {e}')
    familiarity = book['F', j]
    accepted_action = '.-=+12345'
    fam_change = input(f'[{accepted_action}?] ')
    while not fam_change or fam_change not in accepted_action:
        if fam_change == '?':
            print('=== HELP ===')
            print(' .   -- keep current Familiarity Score (FS) unchanged')
            print(' -   -- subtract 1 from FS')
            print(' =   -- add 2 to FS')
            print(' +   -- set FS to 5')
            print(' NUM -- set FS to NUM')
            print(' ?   -- print this help')
            print('============')
            fam_change = input(f'[{accepted_action}?] ')
        else:
            fam_change = input(f'{Colors.BOLD_RED}x{Colors.RESET} '
                               f'[{accepted_action}?] ')
    if fam_change == '.':
        new_fam = familiarity
    elif fam_change == '-':
        new_fam = max(1, familiarity - 1)
    elif fam_change == '=':
        new_fam = min(5, familiarity + 2)
    elif fam_change == '+':
        new_fam = 5
    else:
        new_fam = min(5, max(0, int(fam_change)))
    if new_fam != familiarity:
        book[j] = new_fam
    return new_fam == 1 or new_fam < familiarity


def review_interface(book: VocabBook, indices: ty.List[int]) -> None:
    """Construct the review interface given unfamiliar word indices."""
    T = len(indices)
    print(f'{Colors.BOLD_RED}=== Review ==={Colors.RESET}')
    for i, j in enumerate(indices, 1):
        print()
        word = book['W', j]
        print(f'{Colors.BOLD_RED}->{Colors.RESET} {word} '
              f'{Colors.BOLD_RED}[{i}/{T}]{Colors.RESET}')
        meaning = book['M', j]
        examples = book['E', j]
        print(f'{Colors.BOLD_CYAN}Meaning ->{Colors.RESET} {meaning}')
        for k, e in enumerate(examples, 1):
            print(f'{Colors.BOLD_CYAN}Example #{k} ->{Colors.RESET} {e}')


def main():
    args = make_parser().parse_args()
    cfg = read_config(args)
    colname2ids = parse_csvformat(cfg.csvformat)
    try:
        unfamiliar_indices = []
        with VocabBook(cfg.nbfile, colname2ids) as book:
            fam = book['F']
            sampled_ind = sample_vocab(fam, cfg.total, cfg.min)
            T = len(sampled_ind)
            if (cfg.pronounce and use_requests and cfg.mwapi and cfg.cachedir
                    and sys.platform == 'darwin'):
                prs = load_pronunciation(book, sampled_ind, cfg.mwapi,
                                         cfg.cachedir)
            else:
                prs = {}
            for i, j in enumerate(sampled_ind, 1):
                familiar = qa_interface(book, j, i, T, prs)
                if not familiar:
                    unfamiliar_indices.append(j)
            review_interface(book, unfamiliar_indices)
    except (KeyboardInterrupt, EOFError):
        print('Aborted', file=sys.stderr)


if __name__ == '__main__':
    main()
