"""Stage 4: compare two reads of the same photo."""
import unicodedata


def match_key(title: str) -> str:
    folded = unicodedata.normalize("NFKC", title).casefold()
    return "".join(ch for ch in folded if ch.isalnum())
