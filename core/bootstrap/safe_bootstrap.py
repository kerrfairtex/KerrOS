def safe_bootstrap(supervisor):
    try:
        if hasattr(supervisor.executive, "bind_supervisor"):
            supervisor.executive.bind_supervisor(supervisor)
    except Exception:
        pass

    return supervisor
