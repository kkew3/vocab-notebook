import sqlite3
import datetime

from . import db as m


def test_upsert_word():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    assert m.find_word(conn, 'foo') == {
        'word': 'foo',
        'meaning': 'Foo',
        'pronunciation': None,
        'examples': ['foo bar baz'],
        'familiarity': 4,
    }
    assert m.find_word(conn, 'bar') == {
        'word': 'bar',
        'meaning': 'Bar',
        'pronunciation': 'B-a-r',
        'examples': ['bar baz qux', 'lorem'],
        'familiarity': 5,
    }
    assert m.find_word(conn, 'baz') == {
        'word': 'baz',
        'meaning': 'Baz',
        'pronunciation': 'B-a-z',
        'examples': [],
        'familiarity': 1,
    }
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', ['hello world'], 2)
    m.find_word(conn, 'baz') == {
        'word': 'baz',
        'meaning': 'Baz',
        'pronunciation': 'B-a-z',
        'examples': ['hello world'],
        'familiarity': 2,
    }


def test_insert_memo():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    m.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 5), 5, '+')
    m.insert_memo(conn, 'bar', datetime.datetime(2023, 1, 5), 1, '-')
    m.insert_memo(conn, 'baz', datetime.datetime(2023, 1, 7), 1, 2)
    m.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 8), 5, '-')
    m.insert_memo(conn, 'baz', datetime.datetime(2023, 1, 8), 2, '.')
    sorted(
        m.find_word_memo(conn, 'foo'), key=lambda x: x['date']) == [
            {
                'word': 'foo',
                'date': datetime.datetime(2023, 1, 5),
                'orig_familiarity': 5,
                'action': '+',
            },
            {
                'word': 'foo',
                'date': datetime.datetime(2023, 1, 8),
                'orig_familiarity': 5,
                'action': '-',
            },
        ]
    sorted(
        m.find_word_memo(conn, 'bar'), key=lambda x: x['date']) == [
            {
                'word': 'bar',
                'date': datetime.datetime(2023, 1, 5),
                'orig_familiarity': 1,
                'action': '-',
            },
        ]
    sorted(
        m.find_word_memo(conn, 'baz'), key=lambda x: x['date']) == [
            {
                'word': 'baz',
                'date': datetime.datetime(2023, 1, 7),
                'orig_familiarity': 1,
                'action': 2,
            },
            {
                'word': 'baz',
                'date': datetime.datetime(2023, 1, 8),
                'orig_familiarity': 2,
                'action': '.',
            },
        ]


def test_delete_word():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    m.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 5), 5, '+')
    m.insert_memo(conn, 'bar', datetime.datetime(2023, 1, 5), 1, '-')
    m.insert_memo(conn, 'baz', datetime.datetime(2023, 1, 7), 1, 2)
    m.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 8), 5, '-')
    m.insert_memo(conn, 'baz', datetime.datetime(2023, 1, 8), 2, '.')
    m.delete_word(conn, 'baz')
    assert sorted(
        m.find_all_words(conn), key=lambda x: x['word']) == [
            {
                'word': 'bar',
                'meaning': 'Bar',
                'pronunciation': 'B-a-r',
                'examples': ['bar baz qux', 'lorem'],
                'familiarity': 5,
            },
            {
                'word': 'foo',
                'meaning': 'Foo',
                'pronunciation': None,
                'examples': ['foo bar baz'],
                'familiarity': 4,
            },
        ]
    sorted(
        m.find_word_memo(conn, 'foo'), key=lambda x: x['date']) == [
            {
                'word': 'foo',
                'date': datetime.datetime(2023, 1, 5),
                'orig_familiarity': 5,
                'action': '+',
            },
            {
                'word': 'foo',
                'date': datetime.datetime(2023, 1, 8),
                'orig_familiarity': 5,
                'action': '-',
            },
        ]
    sorted(
        m.find_word_memo(conn, 'bar'), key=lambda x: x['date']) == [
            {
                'word': 'bar',
                'date': datetime.datetime(2023, 1, 5),
                'orig_familiarity': 1,
                'action': '-',
            },
        ]
    sorted(m.find_word_memo(conn, 'baz'), key=lambda x: x['date']) == []


def test_find_all_words():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    assert sorted(
        m.find_all_words(conn), key=lambda x: x['word']) == [
            {
                'word': 'bar',
                'meaning': 'Bar',
                'pronunciation': 'B-a-r',
                'examples': ['bar baz qux', 'lorem'],
                'familiarity': 5,
            },
            {
                'word': 'baz',
                'meaning': 'Baz',
                'pronunciation': 'B-a-z',
                'examples': [],
                'familiarity': 1,
            },
            {
                'word': 'foo',
                'meaning': 'Foo',
                'pronunciation': None,
                'examples': ['foo bar baz'],
                'familiarity': 4,
            },
        ]


def test_find_word():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    assert m.find_word(conn, 'foo') == {
        'word': 'foo',
        'meaning': 'Foo',
        'pronunciation': None,
        'examples': ['foo bar baz'],
        'familiarity': 4,
    }


def test_update_word_familiarity():
    conn = sqlite3.connect(':memory:')
    m.init_db_if_not_exists(conn)
    m.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
    m.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
    m.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
    m.update_word_familiarity(conn, 'foo', 3)
    assert m.find_word(conn, 'foo') == {
        'word': 'foo',
        'meaning': 'Foo',
        'pronunciation': None,
        'examples': ['foo bar baz'],
        'familiarity': 3,
    }
    m.update_word_familiarity(conn, 'qux', 2)
