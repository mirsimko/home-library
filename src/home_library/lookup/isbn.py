def normalize_isbn(text):
    digits = text.replace("-", "").replace(" ", "").upper()
    if not digits.isascii():
        return None
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
        return digits if total % 10 == 0 else None
    if len(digits) == 10 and digits[:9].isdigit() and (digits[9].isdigit() or digits[9] == "X"):
        values = [10 if d == "X" else int(d) for d in digits]
        total = sum(v * (10 - i) for i, v in enumerate(values))
        return digits if total % 11 == 0 else None
    return None
