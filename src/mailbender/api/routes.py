def list_categories(repo) -> list[str]:
    return [c.name for c in repo.list_categories()]


def chat_answer(chat, question: str) -> dict:
    ans = chat.ask(question)
    return {
        "text": ans.text,
        "sources": [{"uid": s.uid, "subject": s.subject} for s in ans.sources],
    }


def run_main(runner) -> dict:
    runner.run_main()
    return {"status": "ok"}


def recent_history(repo, limit: int) -> list[dict]:
    return [
        {"run_type": r.run_type, "uid": r.uid, "step": r.step,
         "result": r.result, "detail": r.detail}
        for r in repo.recent_runs(limit)
    ]


def recent_audit(repo, limit: int) -> list[dict]:
    return [
        {"actor": r.actor, "action": r.action, "target": r.target,
         "result": r.result}
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
