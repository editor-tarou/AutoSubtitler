from .license import is_pro as _is_pro


def _load() -> tuple[str, bool, bool]:
    pro = _is_pro()
    edition = "pro" if pro else "lite"
    return edition, pro, not pro


EDITION, IS_PRO, IS_LITE = _load()


def reload_edition() -> None:
    """Re-read the license and update the module-level flags."""
    global EDITION, IS_PRO, IS_LITE
    from .license import refresh
    refresh()
    EDITION, IS_PRO, IS_LITE = _load()
