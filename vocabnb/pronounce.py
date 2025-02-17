from pathlib import Path
import shutil
import os
from typing import Any
import subprocess
import contextlib
from urllib import parse

import requests
from fake_useragent import UserAgent
from tqdm import tqdm

USE_MPG123 = shutil.which('mpg123') is not None


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


def validate_filename(name: str) -> str:
    tr = {':': '_', '/': '_', '\\': '_', '"': '_'}
    for old, new in tr.items():
        name = name.replace(old, new)
    return name


class PronunciationLoadingError(Exception):
    pass


class PronunciationLoader:
    def __init__(self, api_key: str, todir: Path):
        """
        :param api_key: the Merriam-Webster API key
        :param todir: the directory to store the downloaded audio files, which
               should already exists
        """
        self.api_key = api_key
        self.todir = todir
        self.ua = UserAgent()

    def prepare_requests_kwargs(self, key: bool) -> dict[str, Any]:
        """
        Prepare the keyword arguments to ``requests`` call.

        :param key: whether to include the API key in the request
        """
        proxies = {}
        if 'http_proxy' in os.environ:
            proxies['http_proxy'] = os.environ['http_proxy']
        if 'https_proxy' in os.environ:
            proxies['https_proxy'] = os.environ['https_proxy']
        params = {}
        if key:
            params['key'] = self.api_key
        return {
            'params': params,
            'headers': {
                'user-agent': self.ua.chrome,
            },
            'timeout': 10,
            'proxies': proxies,
        }

    def load(self, word: str) -> Path:
        """
        Load the pronunciation of a word.

        :param word: the word
        :return: the path to the audio file
        :raises PronunciationLoadingError: if loading fails
        """
        word_file = validate_filename(word)
        cachefile = self.todir / (word_file + '.mp3')
        if cachefile.is_file():
            return cachefile

        word_url = (
            'https://dictionaryapi.com/api/v3/references/collegiate/json/'
            + parse.quote(word))
        try:
            # Request the pronunciation file URL.
            resp = requests.get(word_url,
                                **self.prepare_requests_kwargs(True)).json()
            prs_url = None
            for item in resp:
                hw = item['hwi']['hw'].replace('*', '')
                if hw == word:
                    with contextlib.suppress(KeyError, IndexError):
                        prs_url = parse_audio_url(
                            item['hwi']['prs'][0]['sound']['audio'])
            if not prs_url:
                raise PronunciationLoadingError

            # Fetch the audio file given pronunciation URL `prs_url`.
            content = requests.get(
                prs_url, **self.prepare_requests_kwargs(False)).content
            with open(cachefile, 'wb') as outfile:
                outfile.write(content)
            return cachefile
        except (requests.RequestException, TypeError):
            raise PronunciationLoadingError


def prepare_cmds_from_applescript(applescript: str, *argv: str) -> list[str]:
    """
    Prepare the command to execute the given AppleScript.

    :param applescript: the AppleScript
    :param argv: the arguments to the AppleScript
    """
    cmd = ['osascript']
    for stmt in applescript.split('\n'):
        stmt = stmt.strip()
        if stmt:
            cmd.extend(['-e', stmt])
    cmd.extend(argv)
    return cmd


def qtplayer_play_audio():
    """Applescript that plays audio using QuickTime Player."""
    return '''\
on run argv
    set theFile to the first item of argv
    set theFile to POSIX file theFile
    tell application "QuickTime Player"
        set theAudio to open file theFile
        tell theAudio
            set theDuration to duration
            play
        end tell
        delay theDuration + 1
        close theAudio
        quit
    end tell
end run'''


def get_pronounce_process(prs_file: Path) -> subprocess.Popen:
    """
    Return a process that plays the pronunciation.

    :param prs_file: the path to the audio file
    """
    if USE_MPG123:
        cmds = ['mpg123', '-q', str(prs_file)]
    else:
        cmds = prepare_cmds_from_applescript(qtplayer_play_audio(),
                                             str(prs_file))
    return subprocess.Popen(
        cmds, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_pronunciation(words: list[str], mwapi: str, todir: Path):
    """
    Load pronunciation of words given M-W API, and return a dict containing the
    paths to the downloaded audios.
    """
    loader = PronunciationLoader(mwapi, todir)
    prs = {}
    for word in tqdm(words):
        try:
            prs[word] = loader.load(word)
        except PronunciationLoadingError:
            tqdm.write(f'Failed to load pronunciation for word `{word}`')
    return prs
