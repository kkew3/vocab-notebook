import sqlite3
import datetime
import contextlib

from vocabnb import vocabnb as m
from vocabnb import db


class TestVocabBook:
    def test_normal(self):
        conn = sqlite3.connect(':memory:')
        db.init_db_if_not_exists(conn)
        db.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
        db.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
        db.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
        db.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 5), 5, '+')
        with contextlib.suppress(KeyboardInterrupt):
            with m.VocabBook(conn) as book:
                book.add_fam_update(5, 'foo')
                book.add_fam_update(3, 'baz')
                book.add_memo('foo', datetime.datetime(2023, 2, 1), 4, '+')
                book.add_memo('baz', datetime.datetime(2023, 2, 2), 1, 3)
        assert sorted(
            db.find_all_words(conn), key=lambda x: x['word']) == [
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
                    'familiarity': 3,
                },
                {
                    'word': 'foo',
                    'meaning': 'Foo',
                    'pronunciation': None,
                    'examples': ['foo bar baz'],
                    'familiarity': 5,
                },
            ]
        assert sorted(
            db.find_word_memo(conn, 'foo'), key=lambda x: x['date']) == [
                {
                    'word': 'foo',
                    'date': datetime.datetime(2023, 1, 5),
                    'orig_familiarity': 5,
                    'action': '+',
                },
                {
                    'word': 'foo',
                    'date': datetime.datetime(2023, 2, 1),
                    'orig_familiarity': 4,
                    'action': '+',
                },
            ]
        assert db.find_word_memo(conn, 'bar') == []
        assert db.find_word_memo(conn, 'baz') == [
            {
                'word': 'baz',
                'date': datetime.datetime(2023, 2, 2),
                'orig_familiarity': 1,
                'action': 3,
            },
        ]

    def test_interrupted(self):
        conn = sqlite3.connect(':memory:')
        db.init_db_if_not_exists(conn)
        db.upsert_word(conn, 'foo', 'Foo', None, ['foo bar baz'], 4)
        db.upsert_word(conn, 'bar', 'Bar', 'B-a-r', ['bar baz qux', 'lorem'])
        db.upsert_word(conn, 'baz', 'Baz', 'B-a-z', [], 1)
        db.insert_memo(conn, 'foo', datetime.datetime(2023, 1, 5), 5, '+')
        with contextlib.suppress(KeyboardInterrupt):
            with m.VocabBook(conn) as book:
                book.add_fam_update(5, 'foo')
                book.add_fam_update(3, 'baz')
                book.add_memo('foo', datetime.datetime(2023, 2, 1), 4, '+')
                book.add_memo('baz', datetime.datetime(2023, 2, 2), 1, 3)
                raise KeyboardInterrupt
        assert sorted(
            db.find_all_words(conn), key=lambda x: x['word']) == [
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
        assert db.find_word_memo(conn, 'foo') == [
            {
                'word': 'foo',
                'date': datetime.datetime(2023, 1, 5),
                'orig_familiarity': 5,
                'action': '+',
            },
        ]
        assert db.find_word_memo(conn, 'bar') == []
        assert db.find_word_memo(conn, 'baz') == []
