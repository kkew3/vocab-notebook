import sys
from pathlib import Path
import readline
import dataclasses
import contextlib
import sqlite3
import datetime
from typing import Literal, BinaryIO

import numpy as np
import tomli
import colorama
import click
import yaml

from vocabnb import db
try:
    import pronounce_activated
    from vocabnb import pronounce
    USE_PRONOUNCE = True
except ImportError:
    USE_PRONOUNCE = False

colorama.just_fix_windows_console()


def sample_vocab(
    words,
    fam,
    max_total_vocab: int,
    min_non5_vocab: int,
) -> list[str]:
    """
    Sample words according to familiarity scores.

    Sampling rule:

        - Words with score=5 must be sampled, but the order should be shuffled.
          Suppose there are N5 number of such words. Suppose also that there
          are N words in total.
        - For the remaining min(N - N5, max(``max_total_vocab`` - N5,
          ``min_non5_vocab``)) words, sample without replacement, where the
          sampling weights are exp(familiarity scores <=4)

    :param words: the words, string array
    :param fam: the familiarity scores of the vocabulary, int array
    :param max_total_vocab: max number of words to sample
    :param min_non5_vocab: min number of non-5 scored words to sample, which
           takes precedence over ``max_total_vocab``
    :return: list of words
    """
    fam = np.copy(fam)
    n = fam.shape[0]
    j5 = np.nonzero(fam == 5)[0]
    n5 = j5.shape[0]
    n_non5_samples = min(n - n5, max(max_total_vocab - n5, min_non5_vocab))
    fam[j5] = -999999999  # so that j5 words will not be repeatedly sampled
    # See https://timvieira.github.io/blog/post/2019/09/16/algorithms-for-sampling-without-replacement/
    gg = np.random.gumbel(0, 1, size=n)
    gg += fam.astype(float)
    gg *= -1
    jnon5 = np.argsort(gg)[:n_non5_samples]
    j = np.concatenate((j5, jnon5))
    np.random.shuffle(j)
    return words[j].tolist()


@dataclasses.dataclass
class WordDef:
    word: str
    meaning: str
    pronunciation: str | None
    examples: list[str]
    familiarity: int


@dataclasses.dataclass
class WordFam:
    word: str
    familiarity: int


class VocabBook:
    def __init__(self, db_file: Path | sqlite3.Connection):
        if isinstance(db_file, sqlite3.Connection):
            self.conn = db_file
            self._need_close = False
        else:
            self.conn = sqlite3.connect(db_file)
            db.init_db_if_not_exists(self.conn)
            self._need_close = True
        # Words whose familiarity scores have been updated.
        self._updated_word_fam = []
        # Memo
        self._memo = []

    def get_word_def(self, word: str):
        word_def = db.find_word(self.conn, word)
        if word_def:
            return WordDef(**word_def)
        return None

    def get_all_fam(self):
        return [WordFam(**row) for row in db.find_all_words_fam(self.conn)]

    def add_fam_update(self, familiarity: int, word: str):
        self._updated_word_fam.append((familiarity, word))

    def add_memo(
        self,
        word: str,
        date: datetime.datetime,
        orig_familiarity: int,
        action: Literal['+', '=', '-', '.'] | int,
    ):
        self._memo.append((word, date, orig_familiarity, action))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Commit change only if no error happens.
        if exc_type is None and exc_val is None and exc_tb is None:
            with self.conn:
                db.update_word_familiarities(self.conn, self._updated_word_fam,
                                             True)
                db.insert_memos(self.conn, self._memo, True)
        if self._need_close:
            self.conn.close()


class Colors:
    BOLD_GREEN = '\033[1;32m'
    BOLD_CYAN = '\033[1;36m'
    BOLD_RED = '\033[1;31m'
    RESET = '\033[0m'


def qa_interface(
    book: VocabBook,
    i: int,
    word: str,
    T: int,
    prs: dict[str, Path],
) -> bool:
    """
    Construct the Q&A interface for the j-th word in the vocabulary notebook.

    :param book: the vocabulary notebook
    :param i: the question index (1-based)
    :param word: the word to question
    :param T: the total number of questions
    :param prs: pronunciation dict mapping a word index to the pronunciation
           audio path if exists
    :return: ``True`` if the user is familiar with current word
    """
    if word in prs:
        player_emoji = '🔈'
    else:
        player_emoji = ''
    print(f'{Colors.BOLD_GREEN}->{Colors.RESET} {word} '
          f'{Colors.BOLD_GREEN}[{i}/{T}]{Colors.RESET} {player_emoji}')
    if word in prs and USE_PRONOUNCE:
        proc = pronounce.get_pronounce_process(prs[word])
    else:
        proc = contextlib.nullcontext()
    with proc:
        _ = input('[any key] ')
        word_def = book.get_word_def(word)
        assert word_def is not None
        print(f'{Colors.BOLD_CYAN}Meaning ->{Colors.RESET} {word_def.meaning}')
        for k, e in enumerate(word_def.examples, 1):
            print(f'{Colors.BOLD_CYAN}Example #{k} ->{Colors.RESET} {e}')
        familiarity = word_def.familiarity
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
        if fam_change not in '.-=+':
            fam_change = min(5, max(0, int(fam_change)))
        if word in prs and USE_PRONOUNCE:
            proc.terminate()
    today = datetime.datetime.combine(datetime.date.today(), datetime.time())
    book.add_memo(word, today, familiarity, fam_change)
    if fam_change == '.':
        new_fam = familiarity
    elif fam_change == '-':
        new_fam = max(1, familiarity - 1)
    elif fam_change == '=':
        new_fam = min(5, familiarity + 2)
    elif fam_change == '+':
        new_fam = 5
    else:
        new_fam = fam_change
    if new_fam != familiarity:
        book.add_fam_update(new_fam, word)
    return new_fam == 1 or new_fam < familiarity


def review_interface(book: VocabBook, words: list[str]) -> None:
    """Construct the review interface given unfamiliar word indices."""
    T = len(words)
    print(f'{Colors.BOLD_RED}=== Review ==={Colors.RESET}')
    for i, word in enumerate(words, 1):
        print()
        word_def = book.get_word_def(word)
        assert word_def is not None
        print(f'{Colors.BOLD_RED}->{Colors.RESET} {word} '
              f'{Colors.BOLD_RED}[{i}/{T}]{Colors.RESET}')
        print(f'{Colors.BOLD_CYAN}Meaning ->{Colors.RESET} {word_def.meaning}')
        for k, e in enumerate(word_def.examples, 1):
            print(f'{Colors.BOLD_CYAN}Example #{k} ->{Colors.RESET} {e}')


def read_config(ctx, _param, value):
    with contextlib.suppress(FileNotFoundError):
        with open(value, 'rb') as infile:
            config = tomli.load(infile)
        if 'cachedir' in config:
            config['cachedir'] = Path(config['cachedir']).expanduser()
        config['dbfile'] = Path(config['dbfile']).expanduser()
        ctx.default_map = config


if USE_PRONOUNCE:
    pronounce_opt = click.option(
        '-P',
        '--pronounce/--no-pronounce',
        'do_pronounce',
        help=('To pronounce aloud every sampled word as long as '
              'there\'s a pronunciation for it; note that this will slow '
              'down the initialization of the app.'),
    )
else:
    pronounce_opt = click.option(
        ' /--no-pronounce',
        'do_pronounce',
        help='Pronunciation has been disabled.')
config_file_opt = click.option(
    '-f',
    '--config',
    'config_file',
    default=Path('~/.config/vocabnb/config.toml').expanduser(),
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    callback=read_config,
    is_eager=True,
    expose_value=False,
    help='Read config from FILE.',
)
dbfile_opt = click.option(
    '-d',
    '--dbfile',
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    help='The database file.',
)


@click.command(
    context_settings={'auto_envvar_prefix': 'VOCABNB'},
    help='Vocabulary notebook sampler.',
)
@config_file_opt
@click.option(
    '-T',
    '--total',
    'total_sample',
    type=int,
    help='Total number of words to sample.',
)
@click.option(
    '-m',
    '--min',
    'min_sample',
    type=int,
    help='Min number of non-5 familiarity scored words to sample',
)
@pronounce_opt
@dbfile_opt
@click.option(
    '-C',
    '--cachedir',
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help=('If specified neither here nor in the configuration file, '
          'no cache will be made.'),
)
@click.option(
    '--mwapi',
    'api_key',
    metavar='API_KEY',
    help='The Merriam-Webster API key for pronouncing aloud.',
)
def sample(
    total_sample: int,
    min_sample: int,
    do_pronounce: bool,
    dbfile: Path,
    cachedir: Path | None,
    api_key: str | None,
):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        click.echo('ERROR: stdin and stdout must be interactive', err=True)
        sys.exit(1)
    try:
        unfamiliar_words = []
        with VocabBook(dbfile) as book:
            word_fams = book.get_all_fam()
            words = np.array([x.word for x in word_fams])
            fam = np.array([x.familiarity for x in word_fams])
            sampled_words = sample_vocab(words, fam, total_sample, min_sample)
            total = len(sampled_words)
            if do_pronounce and USE_PRONOUNCE and api_key and cachedir:
                cachedir.mkdir(parents=True, exist_ok=True)
                prs = pronounce.load_pronunciation(sampled_words, api_key,
                                                   cachedir)
            else:
                prs = {}
            for i, word in enumerate(sampled_words, 1):
                familiar = qa_interface(book, i, word, total, prs)
                if not familiar:
                    unfamiliar_words.append(word)
            review_interface(book, unfamiliar_words)
    except (KeyboardInterrupt, EOFError):
        click.echo('Aborted', err=True)
        sys.exit(130)


@click.command()
@config_file_opt
@dbfile_opt
@click.argument('word')
def query(dbfile: Path, word: str):
    """
    Query word definition.
    """
    with VocabBook(dbfile) as book:
        word_def = book.get_word_def(word)
        if word_def:
            yaml.dump(
                dataclasses.asdict(word_def),
                stream=sys.stdout,
                allow_unicode=True,
                sort_keys=False)


@click.command()
@config_file_opt
@dbfile_opt
@click.argument('word')
def delete(dbfile: Path, word: str):
    """
    Delete word definition.
    """
    with VocabBook(dbfile) as book:
        db.delete_word(book.conn, word)


@click.command()
@config_file_opt
@dbfile_opt
@click.argument('word_def_file', type=click.File('rb'))
def upsert(dbfile: Path, word_def_file: BinaryIO):
    """
    Upsert word definition by reading word definition yaml, as written by
    `query` command. Pass in a yaml file or `-` to read from stdin.
    """
    word_def_dict = yaml.safe_load(word_def_file)
    if not isinstance(word_def_dict, dict):
        click.echo('ERROR: word_def_file should contain a dict', err=True)
        sys.exit(1)
    word_def_dict.setdefault('pronunciation')
    word_def_dict.setdefault('familiarity', 5)
    word_def_dict.setdefault('examples', [])
    word_def = WordDef(**word_def_dict)
    with VocabBook(dbfile) as book:
        db.upsert_word(book.conn, word_def.word, word_def.meaning,
                       word_def.pronunciation, word_def.examples,
                       word_def.familiarity)


@click.command()
def upsert_template():
    """Print the yaml template required by `upsert`."""
    template = '''\
# The word to upsert.
word: <word>
# The meaning.
meaning: <meaning>
# The pronunciation (optional, nullable).
pronunciation: null
# A list of examples (optinoal).
examples:
- <example1>
- <example2>
# The familiarity (optional).
familiarity: 5'''
    click.echo(template)


@click.command(name='ls')
@config_file_opt
@dbfile_opt
def list_words(dbfile: Path):
    """List all words in arbitrary order."""
    with VocabBook(dbfile) as book:
        for word_fam in book.get_all_fam():
            click.echo(word_fam.word)


@click.group()
def main():
    """
    The vocabulary book cli.
    """


main.add_command(sample)
main.add_command(query)
main.add_command(delete)
main.add_command(upsert)
main.add_command(upsert_template)
main.add_command(list_words)
