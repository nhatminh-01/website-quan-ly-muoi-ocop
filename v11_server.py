"""v1.1 application launcher.

Loads the login-theme hooks explicitly before starting the composed app server.
This avoids relying on Python's optional automatic sitecustomize discovery,
which is not guaranteed for every local Windows environment.
"""
from __future__ import annotations

import runpy

import sitecustomize  # noqa: F401  # Explicitly applies the v1.1 login/remember-login hooks.


if __name__ == "__main__":
    runpy.run_module("app_server", run_name="__main__")
