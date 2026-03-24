import random
import string

def generate_readable_id(prefix: str, length: int = 8) -> str:
    """
    Generate a human-readable ID with a prefix and random alphanumeric characters.
    Example: ACC-X7R2K9L1
    """
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(random.choice(chars) for _ in range(length))
    return f"{prefix}-{random_part}"
