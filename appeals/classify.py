"""Автоматическое определение категории и причины по ключевым фразам (Д1)."""

from collections import defaultdict
from dataclasses import dataclass, field

from .text import normalize, phrase_stems, phrase_words, stem, tokens

MIN_SCORE = 2  # меньше двух баллов: одно слабое слово, категорию не ставим
MIN_LEAD = 1.5  # победитель должен опережать вторую категорию в полтора раза
WINDOW_EXTRA = 2  # на сколько слов многословная фраза может растянуться в тексте
WORD_FUZZY_MIN_LEN = 5  # опечатка ищется в словах от пяти букв: «курер» вместо «курьер»
STEM_FUZZY_MIN_LEN = 6  # разные формы одного слова сравниваются по основам от шести букв: «треснут» и «треснул»
PREFIX_MIN_LEN = 4  # основа из текста может быть длиннее основы фразы, если у фразы от четырёх букв
PREFIX_EXTRA = 2  # и не больше чем на две буквы: «разбит» стеммер режет до «разб», «разбитая» до «разбит»
NEG = "не"


def _deletes(word):
    return {word[:i] + word[i + 1 :] for i in range(len(word))}


def one_edit(a, b):
    """Строки различаются ровно одной правкой: пропуск, вставка, замена или перестановка соседних букв."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) < len(b):
        return a[i:] == b[i + 1 :]
    if a[i + 1 :] == b[i + 1 :]:
        return True
    return i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2 :] == b[i + 2 :]


def _index(words, min_len):
    """Вариант слова без одной буквы -> исходные слова. Так близкое слово находится без перебора словаря."""
    index = defaultdict(set)
    for w in words:
        if len(w) >= min_len:
            index[w].add(w)
            for v in _deletes(w):
                index[v].add(w)
    return index


def _close(index, word, same_length=False):
    """Слова из индекса на расстоянии одной правки. Первая буква должна совпасть:
    «позвонил» и «дозвониться» разные слова, а не опечатка."""
    found = set()
    for v in _deletes(word) | {word}:
        for w in index.get(v, ()):
            if w[0] == word[0] and (not same_length or len(w) == len(word)) and one_edit(word, w):
                found.add(w)
    return found


def _phrase_parts(rule_stems):
    """Фраза как список (основа, нужно ли «не» прямо перед ней)."""
    parts = []
    negated = False
    for s in rule_stems:
        if s == NEG:
            negated = True
            continue
        parts.append((s, negated))
        negated = False
    if negated:  # фраза кончается на «не», такого в словаре нет, но не теряем слово
        parts.append((NEG, False))
    return parts


@dataclass
class Rule:
    reason_id: int
    category_id: int
    phrase: str
    weight: int
    stems: list
    parts: list = field(default_factory=list)

    def __post_init__(self):
        self.parts = _phrase_parts(self.stems)


@dataclass
class Result:
    category_id: int | None = None
    reason_id: int | None = None
    score: float = 0
    # Все сработавшие фразы, в том числе других категорий: оператор видит, из чего выбирали.
    matches: list = field(default_factory=list)


class Classifier:
    def __init__(self, rules):
        self.rules = rules
        self.vocab = {s for rule in rules for s in rule.stems}
        self.word_stem = {w: stem(w) for rule in rules for w in phrase_words(rule.phrase)}
        self.word_index = _index(self.word_stem, WORD_FUZZY_MIN_LEN)
        self.stem_index = _index(self.vocab, STEM_FUZZY_MIN_LEN)

    @classmethod
    def from_db(cls):
        from .models import KeywordRule

        rules = []
        active = KeywordRule.objects.filter(reason__is_active=True, reason__category__is_active=True)
        for r in active.select_related("reason").order_by("reason_id", "id"):
            rule_stems = phrase_stems(r.phrase)
            if rule_stems:
                rules.append(Rule(r.reason_id, r.reason.category_id, r.phrase, r.weight, rule_stems))
        return cls(rules)

    def _known(self, word, word_stem):
        """Какие основы словаря может означать слово текста."""
        found = set()
        # Опечатку ищем в самом слове: у слова с опечаткой стеммер часто режет окончание не так.
        if len(word) >= WORD_FUZZY_MIN_LEN:
            found |= {self.word_stem[w] for w in _close(self.word_index, word)}
        # Основа и её начало без одной-двух последних букв: стеммер режет формы одного слова по-разному.
        for k in range(PREFIX_EXTRA + 1):
            part = word_stem[: len(word_stem) - k]
            if k and len(part) < PREFIX_MIN_LEN:
                break
            if part in self.vocab:
                found.add(part)
            if len(part) >= STEM_FUZZY_MIN_LEN:
                # У укороченной основы допускаем только замену и перестановку, иначе «описа» сойдётся с «отписа».
                found |= _close(self.stem_index, part, same_length=k > 0)
        return found

    @staticmethod
    def _phrase_found(positions, parts):
        """Все слова фразы есть в окне длиной (слов во фразе + WINDOW_EXTRA), порядок не важен.
        Если во фразе «не» стоит перед словом, в тексте оно тоже должно стоять прямо перед ним."""
        neg_at = set(positions.get(NEG, ()))
        candidates = []
        for s, negated in parts:
            found = [p for p in positions.get(s, ()) if not negated or p - 1 in neg_at]
            if not found:
                return False
            candidates.append([(p - 1 if negated else p, p) for p in found])
        if len(candidates) == 1:
            return True
        width = sum(2 if negated else 1 for _, negated in parts) + WINDOW_EXTRA
        starts = sorted({first for options in candidates for first, _ in options})
        for start in starts:
            end = start + width - 1
            if all(any(first >= start and last <= end for first, last in options) for options in candidates):
                return True
        return False

    def classify(self, text):
        positions = defaultdict(list)
        for i, word in enumerate(tokens(text)):
            for s in self._known(word, stem(word)):
                positions[s].append(i)

        reason_score = defaultdict(int)
        category_score = defaultdict(int)
        reason_category = {}
        matches = []
        for rule in self.rules:
            if self._phrase_found(positions, rule.parts):
                reason_score[rule.reason_id] += rule.weight
                category_score[rule.category_id] += rule.weight
                reason_category[rule.reason_id] = rule.category_id
                matches.append({"reason": rule.reason_id, "phrase": rule.phrase, "weight": rule.weight})

        result = Result(matches=matches)
        if not category_score:
            return result
        ranked = sorted(category_score.items(), key=lambda kv: -kv[1])
        best_id, best = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        result.score = best
        if best < MIN_SCORE or (second and best < MIN_LEAD * second):
            return result
        result.category_id = best_id
        # Внутри категории причина с наибольшим баллом, при равенстве та, что раньше в справочнике.
        reasons = [rid for rid, cid in reason_category.items() if cid == best_id]
        result.reason_id = max(reasons, key=lambda rid: (reason_score[rid], -rid))
        return result


def recategorize(queryset, classifier=None, batch_size=500):
    """Пересчитывает text_norm и автокатегорию у обращений без ручной категории. Возвращает число изменённых."""
    from .models import Appeal

    classifier = classifier or Classifier.from_db()
    fields = ["text_norm", "category", "reason", "category_source", "category_score", "category_matches"]
    changed = 0
    buffer = []
    for appeal in queryset.exclude(category_source=Appeal.Source.MANUAL).iterator(chunk_size=batch_size):
        before = (appeal.category_id, appeal.reason_id)
        appeal.text_norm = normalize(appeal.full_text)
        appeal.apply_classification(classifier.classify(appeal.full_text))
        if (appeal.category_id, appeal.reason_id) != before:
            changed += 1
        buffer.append(appeal)
        if len(buffer) >= batch_size:
            Appeal.objects.bulk_update(buffer, fields)
            buffer = []
    if buffer:
        Appeal.objects.bulk_update(buffer, fields)
    return changed
