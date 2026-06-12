def list_categories(repo) -> list[str]:
    return [c.name for c in repo.list_categories()]


def chat_answer(chat, question: str) -> dict:
    ans = chat.ask(question)
    return {
        "text": ans.text,
        "sources": [{"uid": s.uid, "subject": s.subject} for s in ans.sources],
    }


RUN_TYPES = {"main", "style", "feedback"}


def run(runner, run_type: str = "main") -> dict:
    dispatch = {
        "main": "run_main",
        "style": "run_style",
        "feedback": "run_feedback",
    }
    getattr(runner, dispatch[run_type])()
    return {"status": "ok", "run_type": run_type}


def _iso(dt):
    return dt.isoformat() if dt else None


def recent_history(repo, limit: int) -> list[dict]:
    return [
        {"run_type": r.run_type, "uid": r.uid, "step": r.step,
         "result": r.result, "detail": r.detail,
         "created_at": _iso(r.created_at)}
        for r in repo.recent_runs(limit)
    ]


def recent_audit(repo, limit: int) -> list[dict]:
    return [
        {"actor": r.actor, "action": r.action, "target": r.target,
         "result": r.result, "created_at": _iso(r.created_at)}
        for r in repo.recent_audit(limit)
    ]


def priorities(repo) -> list[dict]:
    return [
        {"uid": p.uid, "priority": p.priority, "category": p.category}
        for p in repo.processed_by_priority()
    ]


def list_mappings(repo) -> list[dict]:
    return [
        {"category": m.category_name, "folder": m.target_folder}
        for m in repo.list_mappings()
    ]


def add_mapping(repo, category: str, folder: str) -> dict:
    repo.add_mapping(category, folder)
    return {"category": category, "folder": folder}


def remove_mapping(repo, category: str) -> dict:
    return {"removed": repo.remove_mapping(category)}


def add_category(repo, name: str, description: str = "") -> dict:
    repo.add_category(name, description)
    return {"name": name, "description": description}


def remove_category(repo, name: str) -> bool:
    return repo.remove_category(name)
