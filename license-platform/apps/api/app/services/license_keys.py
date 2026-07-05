from __future__ import annotations

import random
import string


def generate_license_key(product_prefix: str = "LIC") -> str:
    chunks = [
        "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        for _ in range(3)
    ]
    return f"{product_prefix}-{'-'.join(chunks)}"
