from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROUTES = {
    "/": "index.html",
    "/power-rankings/": "power-rankings/index.html",
    "/simulations/": "simulations/index.html",
    "/scenarios/": "scenarios/index.html",
    "/efficiency/": "efficiency/index.html",
    "/champions/": "champions/index.html",
    "/bootymen/": "bootymen/index.html",
    "/records/": "records/index.html",
}


def _relative_prefix(output_file: Path) -> str:
    depth = len(output_file.parent.parts)
    return "../" * depth


def _rewrite_links(html: str, output_file: Path) -> str:
    prefix = _relative_prefix(output_file)

    html = re.sub(r'((?:href|src)=["\'])/static/', rf'\1{prefix}static/', html)
    html = re.sub(r'((?:href|src)=["\'])/logos/', rf'\1{prefix}logos/', html)

    for route, target in ROUTES.items():
        href = f'{prefix}{target}'
        html = html.replace(f'href="{route}"', f'href="{href}"')
        html = html.replace(f"href='{route}'", f"href='{href}'")

    return html


def export_static(output_dir: Path, clean: bool = True) -> None:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    from flask_app import app

    with app.test_client() as client:
        for route, target in ROUTES.items():
            response = client.get(route)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Could not export {route}: HTTP {response.status_code}"
                )

            output_file = output_dir / target
            output_file.parent.mkdir(parents=True, exist_ok=True)
            html = response.get_data(as_text=True)
            output_file.write_text(
                _rewrite_links(html=html, output_file=Path(target)),
                encoding="utf-8"
            )

    shutil.copytree("static", output_dir / "static", dirs_exist_ok=True)
    shutil.copytree("logos", output_dir / "logos", dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the Flask app to static HTML files."
    )
    parser.add_argument(
        "--output",
        default="docs",
        help="Output directory for the static site. Defaults to docs.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete the output directory before exporting.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    export_static(output_dir=output_dir, clean=not args.no_clean)
    print(f"Exported static site to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
