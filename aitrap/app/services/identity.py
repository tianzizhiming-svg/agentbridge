import secrets


def generate_azone_id() -> str:
    """Generate a unique Azone identity: azone_xxxxxxxxxx"""
    return f"azone_{secrets.token_hex(5)}"
