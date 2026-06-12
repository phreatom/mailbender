"""Default category set and seeding helper.

The standard set is a starting point — categories are freely editable at runtime
via the repository / CLI. "Antwort nötig" is the category that triggers automatic
reply-draft generation, so it must always be present in the defaults.
"""

DEFAULT_CATEGORIES = [
    ("Antwort nötig", "E-Mails, die eine persönliche Antwort erfordern"),
    ("Newsletter", "Abonnierte Newsletter und Mailinglisten"),
    ("Rechnung", "Rechnungen, Zahlungen und Belege"),
    ("Werbung", "Werbung und Marketing-Mails"),
    ("Benachrichtigung", "Automatische Benachrichtigungen und Systemmeldungen"),
    ("Sonstiges", "Alles andere"),
]


def seed_default_categories(repo) -> int:
    """Add any missing default categories. Idempotent.

    Returns the number of categories newly added (0 if all already present).
    """
    existing = {c.name for c in repo.list_categories()}
    added = 0
    for name, description in DEFAULT_CATEGORIES:
        if name in existing:
            continue
        repo.add_category(name, description)
        added += 1
    return added
