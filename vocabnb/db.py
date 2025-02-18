import json
from sqlite3 import Connection
import datetime
import contextlib
from typing import Literal

TABLE_NAME_WORDS = 'words'
TABLE_NAME_MEMO = 'memo'


def init_db_if_not_exists(conn: Connection):
    with conn:
        conn.execute('PRAGMA foreign_keys = ON')
    with conn:
        conn.execute(f'''\
CREATE TABLE IF NOT EXISTS {TABLE_NAME_WORDS} (
    word TEXT PRIMARY KEY,
    meaning TEXT NOT NULL,
    pronunciation TEXT,
    examples TEXT,
    familiarity INTEGER NOT NULL
)''')
        conn.execute(f'''\
CREATE TABLE IF NOT EXISTS {TABLE_NAME_MEMO} (
    word TEXT,
    date TEXT,
    orig_familiarity INTEGER NOT NULL,
    action TEXT NOT NULL,
    PRIMARY KEY (word, date),
    FOREIGN KEY (word) REFERENCES {TABLE_NAME_WORDS}(word)
)''')


def upsert_word(
    conn: Connection,
    word: str,
    meaning: str,
    pronunciation: str | None,
    examples: list[str],
    familiarity: int = 5,
):
    """
    Upsert a word.

    :param conn: the sqlite3 connection
    :param word: the word to insert
    :param meaning: the meaning of the word
    :param pronunciation: the pronunciation of the word
    :param examples: examples of the word
    :param familiarity: 5 means unfamiliar, 1 means familiar
    """
    with conn:
        conn.execute(
            f'''\
INSERT INTO {TABLE_NAME_WORDS} (word, meaning, pronunciation, examples, familiarity)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(word) DO UPDATE SET
    meaning = excluded.meaning,
    pronunciation = excluded.pronunciation,
    examples = excluded.examples,
    familiarity = excluded.familiarity''',
            (word, meaning, pronunciation, json.dumps(examples), familiarity))


def insert_memo(
    conn: Connection,
    word: str,
    date: datetime.datetime,
    orig_familiarity: int,
    action: Literal['+', '=', '-', '.'] | int,
    within_transaction: bool = False,
):
    """
    Insert a memo.

    :param conn: the sqlite3 connection
    :param word: the word to insert
    :param date: the date of the memo
    :param orig_familiarity: the original familiarity of the word
    :param action: the memo action taken on the word
    :param within_transaction: True if the invocation of this function is
           already in a `with conn` statement
    """
    trans = contextlib.nullcontext() if within_transaction else conn
    with trans:
        conn.execute(
            f'''\
INSERT INTO {TABLE_NAME_MEMO} (word, date, orig_familiarity, action)
VALUES (?, ?, ?, ?)''',
            (word, date.isoformat(), orig_familiarity, str(action)))


def insert_memos(
    conn: Connection,
    args: list[tuple[str, datetime.datetime, int,
                     Literal['+', '=', '-', '.'] | int]],
    within_transaction: bool = False,
):
    """
    Insert memos in batch.

    :param conn: the sqlite3 connection
    :param args: list of (word, date, orig_familiarity, action)
    :param within_transaction: True if the invocation of this function is
           already in a `with conn` statement
    """
    trans = contextlib.nullcontext() if within_transaction else conn
    with trans:
        conn.executemany(
            f'''\
INSERT INTO {TABLE_NAME_MEMO} (word, date, orig_familiarity, action)
VALUES (?, ?, ?, ?)''', args)


def delete_word(conn: Connection, word: str):
    """
    Delete a word.

    :param conn: the sqlite3 connection
    :param word: the word to delete
    """
    with conn:
        conn.execute(f'DELETE FROM {TABLE_NAME_MEMO} WHERE word = ?', (word,))
        conn.execute(f'DELETE FROM {TABLE_NAME_WORDS} WHERE word = ?', (word,))


def find_all_words(conn: Connection):
    """
    Find all word definitions in arbitrary order.

    :param conn: the sqlite3 connection
    :return: a list of word definitions
    """
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {TABLE_NAME_WORDS}')
    results = cur.fetchall()
    return [{
        'word': row[0],
        'meaning': row[1],
        'pronunciation': row[2],
        'examples': json.loads(row[3]),
        'familiarity': row[4],
    } for row in results]


def find_all_words_fam(conn: Connection):
    """
    Find all words and their familiarities in arbitrary order.

    :param conn: the sqlite3 connection
    :return: a list of word familiarities
    """
    cur = conn.cursor()
    cur.execute(f'SELECT word, familiarity FROM {TABLE_NAME_WORDS}')
    results = cur.fetchall()
    return [{'word': row[0], 'familiarity': row[1]} for row in results]


def find_word(conn: Connection, word: str):
    """
    Find a word definition.

    :param conn: the sqlite3 connection
    :param word: the word to find
    :return: the word definition if found, or None
    """
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {TABLE_NAME_WORDS} WHERE word = ?', (word,))
    result = cur.fetchone()
    if result is not None:
        return {
            'word': result[0],
            'meaning': result[1],
            'pronunciation': result[2],
            'examples': json.loads(result[3]),
            'familiarity': result[4],
        }
    return None


def int_or_str(value: str):
    try:
        return int(value)
    except ValueError:
        return value


def find_word_memo(conn: Connection, word: str):
    """
    Find all memo of a word.

    :param conn: the sqlite3 connection
    :param word: the word whose memo is to find
    """
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {TABLE_NAME_MEMO} WHERE word = ?', (word,))
    results = cur.fetchall()
    return [{
        'word': row[0],
        'date': datetime.datetime.fromisoformat(row[1]),
        'orig_familiarity': row[2],
        'action': int_or_str(row[3])
    } for row in results]


def update_word_familiarity(
    conn: Connection,
    familiarity: int,
    word: str,
    within_transaction: bool = False,
):
    """
    Update the familiarity of a word.

    :param conn: the sqlite3 connection
    :param familiarity: the new familiarity
    :param word: the word to update
    :param within_transaction: True if the invocation of this function is
           already in a `with conn` statement
    """
    trans = contextlib.nullcontext() if within_transaction else conn
    with trans:
        conn.execute(
            f'UPDATE {TABLE_NAME_WORDS} SET familiarity = ? WHERE word = ?',
            (familiarity, word))


def update_word_familiarities(
    conn: Connection,
    args: list[tuple[int, str]],
    within_transaction: bool = False,
):
    """
    Update familiarities in batch.

    :param conn: the sqlite3 connection
    :param args: list of (familiarity, word).
    :param within_transaction: True if the invocation of this function is
           already in a `with conn` statement
    """
    trans = contextlib.nullcontext() if within_transaction else conn
    with trans:
        conn.executemany(
            f'UPDATE {TABLE_NAME_WORDS} SET familiarity = ? WHERE word = ?',
            args)
