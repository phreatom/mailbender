import sys


def test_thin_cli_does_not_import_server_modules():
    # Drop any server modules a previous test imported, then import the CLI.
    server_prefixes = (
        "mailbender.store", "mailbender.imap", "mailbender.api",
        "mailbender.scheduler", "mailbender.llm", "mailbender.pipeline",
        "mailbender.config", "mailbender.chat", "mailbender.audit",
    )
    for name in list(sys.modules):
        if name.startswith(server_prefixes):
            del sys.modules[name]
    if "mailbender.cli.main" in sys.modules:
        del sys.modules["mailbender.cli.main"]

    import mailbender.cli.main  # noqa: F401

    leaked = [n for n in sys.modules if n.startswith(server_prefixes)]
    assert leaked == [], f"thin CLI imported server modules: {leaked}"
