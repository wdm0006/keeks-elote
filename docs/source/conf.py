"""Sphinx configuration for the keeks-elote documentation.

The API reference pages are hand-written reStructuredText (no autodoc), so the
docs build never imports keeks_elote or its dependencies -- a docs build needs
nothing but Sphinx and the wabi theme from ``docs/requirements.txt``.
"""

import re
from pathlib import Path

# -- Project information -----------------------------------------------------

# The version is read out of pyproject.toml (hatchling's source of truth)
# rather than duplicated here or imported from the package.
_project_toml = Path(__file__).resolve().parents[2] / "pyproject.toml"
_version = re.search(r'^version = "([^"]+)"', _project_toml.read_text(encoding="utf-8"), re.MULTILINE)
if _version is None:
    raise RuntimeError("could not read the project version from pyproject.toml")
version = _version.group(1)
release = version

project = "keeks-elote"
copyright = "2026, Will McGinnis"
author = "Will McGinnis"

# -- General configuration ---------------------------------------------------

# Hand-written API pages: no autodoc, no autosummary. References to keeks and
# elote objects stay inline literals rather than intersphinx links, keeping the
# build hermetic (no network fetches).
extensions = []

# -- Options for HTML output -------------------------------------------------

html_theme = "wabi_sphinx_theme"

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "wabi_sphinx_theme.pygments_style.WabiStyle"

# Theme options, mirroring the keeks docs. There is no custom docs domain for
# keeks-elote, so the theme's docs-link options are left unset.
html_theme_options = {
    "site_title": "McGinnis, Will",
    "site_url": "https://mcginniscommawill.com",
    "nav_links": [
        {"label": "Guides", "url": "https://mcginniscommawill.com/guides/"},
        {"label": "Topics", "url": "https://mcginniscommawill.com/topics/"},
        {"label": "Blog", "url": "https://mcginniscommawill.com/posts/"},
        {"label": "About", "url": "https://mcginniscommawill.com/about/"},
        {"label": "Free Coffee", "url": "https://mcginniscommawill.com/coffee/"},
        {"label": "OSS", "url": "https://mcginniscommawill.com/oss/"},
    ],
    "show_breadcrumbs": True,
    "show_home_breadcrumb": True,
    "twitter_site": "@willmcginniser",
}

# No _static directory ships with this site; an explicit empty list keeps
# Sphinx from warning about a missing path under -W.
html_static_path = []

# Set the title of the documentation
html_title = "Keeks-Elote"
