"""Нормализация текста: нижний регистр, ё как е, слова, основы русского стеммера Snowball."""

import re
import threading
from functools import lru_cache

import snowballstemmer

WORD_RE = re.compile(r"[а-яa-z0-9]+")

# Служебные слова не обязаны стоять в тексте, чтобы совпала ключевая фраза.
# Частица «не» сюда не входит: «приходит» и «не приходит» означают разное.
STOP_WORDS = frozenset(
    "а и но или в во на по с со к ко у о об от до из за для при про через как что же ли бы то".split()
)

# Стеммер хранит состояние внутри объекта, поэтому у каждого потока свой экземпляр.
_local = threading.local()


def _stemmer():
    if not hasattr(_local, "stemmer"):
        _local.stemmer = snowballstemmer.stemmer("russian")
    return _local.stemmer


def tokens(text):
    return WORD_RE.findall(text.lower().replace("ё", "е"))


@lru_cache(maxsize=100_000)
def stem(word):
    return _stemmer().stemWord(word)


def stems(text):
    return [stem(word) for word in tokens(text)]


def normalize(text):
    """Строка основ через пробел, в таком виде текст хранится в Appeal.text_norm."""
    return " ".join(stems(text))


def phrase_words(phrase):
    """Слова ключевой фразы без служебных. Если фраза состоит только из них, они остаются."""
    words = tokens(phrase)
    return [w for w in words if w not in STOP_WORDS] or words


def phrase_stems(phrase):
    return [stem(w) for w in phrase_words(phrase)]
