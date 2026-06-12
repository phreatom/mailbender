def list_categories(repo) -> list[str]:
    return [c.name for c in repo.list_categories()]
