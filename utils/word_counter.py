import re
from collections import Counter


def count_words(text: str) -> dict:
    text = text.lower()
    words = re.findall(r"\b[a-záéíóúüñ\w]+\b", text, re.UNICODE)
    words = [w for w in words if len(w) > 1]
    return dict(Counter(words))


def merge_counts(*count_dicts) -> dict:
    merged = Counter()
    for d in count_dicts:
        merged.update(d)
    return dict(merged)
