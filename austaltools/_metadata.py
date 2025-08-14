# austaltools/__init__.py or austaltools/_metadata.py
from datetime import datetime
try:
    from importlib.metadata import metadata, version
except ImportError:
    # Python < 3.8
    from importlib_metadata import metadata, version

__title__ = "austaltools"

year = datetime.now().year
__copyright__ = f'(C) 2022-{year} Clemens Drüe'

def get_metadata():
    """Get package metadata from pyproject.toml"""
    meta = metadata(__title__)
    return {
        '__version__': version(__title__),
        '__author__': meta.get("Author", ""),
        '__author_email__': meta.get("Author-email", ""),
        '__description__': meta.get("Summary", ""),
        '__url__': meta.get("Home-page", ""),
        '__license__': meta.get("License", ""),
    }

# Make variables available at module level
_meta = get_metadata()
__version__ = _meta['__version__']
__author__ = _meta['__author__']
__author_email__ = _meta['__author_email__']
__description__ = _meta['__description__']
__url__ = _meta['__url__']
__license__ = _meta['__license__']

# Usage: from austaltools import __author__, __version__