"""mdview — browser-served interactive visualization of MD systems.

The backend lists and serves molecular structure files from a configured data
root; the browser-side Mol* viewer renders them. Designed for single-user access
over an SSH tunnel (bind 127.0.0.1, no auth).
"""

__version__ = "0.1.0"
