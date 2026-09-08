from app.supervisor import PROJECT_ROOT, commands


def test_supervisor_starts_all_required_services():
    configured = commands()
    assert set(configured) == {"bot", "worker", "scheduler", "api"}
    assert all(
        command[0].startswith(str(PROJECT_ROOT / ".venv")) for command in configured.values()
    )
    assert "--pool=solo" in configured["worker"]
