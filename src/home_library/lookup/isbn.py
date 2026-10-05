def normalize_isbn(text):
    digits = text.replace("-", "").replace(" ", "")
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
        if total % 10 != 0:
            return None
    return digits
