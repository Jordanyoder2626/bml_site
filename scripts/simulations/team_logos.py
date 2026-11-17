"""Find local team artwork, including extensionless images and SVGs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def find_team_logo(team, root=ROOT):
    directory = Path(root) / 'logos'
    candidates = [directory / f'{team}{extension}'
                  for extension in ('.png', '.jpg', '.jpeg', '', '.svg')]
    return next((path for path in candidates if path.is_file() and path.stat().st_size), None)
