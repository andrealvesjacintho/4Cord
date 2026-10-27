#!/usr/bin/env python3
"""Regressao: fechar a janela de login deve encerrar o processo.

Sem isso, o processo fica sem janela, segura o instance.lock e a proxima
tentativa de abrir o 4Cord apenas imprime "4Cord ja esta aberto".
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402


def main():
    state = {"timeout": False, "closed": False}
    application = app.App(mock=False, token=None)
    application.start()

    def close_login():
        if application.login is None:
            state["timeout"] = True
            Gtk.main_quit()
            return False
        application.login.destroy()
        state["closed"] = True
        return False

    def timeout():
        state["timeout"] = True
        Gtk.main_quit()
        return False

    GLib.timeout_add(500, close_login)
    GLib.timeout_add(3000, timeout)
    Gtk.main()

    if state["timeout"] or not state["closed"]:
        print("LOGIN_CLOSE_FAIL", state)
        return 1
    print("LOGIN_CLOSE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
