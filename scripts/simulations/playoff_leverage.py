"""Render a playoff leverage chart from explicit conditional simulation odds."""

import argparse
import csv
import math
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scripts.simulations.team_logos import find_team_logo

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import is_color_like
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Polygon


BACKGROUND = '#f0f0ef'
LOSS = '#ff7200'
WIN = '#008fd5'


def circular_logo(path, size=128):
    """Center-crop all artwork to the same circular badge, in memory."""
    if Path(path).suffix.lower() == '.svg':
        from resvg_py import svg_to_bytes
        source = BytesIO(svg_to_bytes(svg_path=str(path), width=256, height=256))
    else:
        source = path
    with Image.open(source) as original:
        image = ImageOps.fit(ImageOps.exif_transpose(original).convert('RGBA'),
                             (size, size), method=Image.Resampling.LANCZOS)
    badge = Image.new('RGBA', (size, size), 'white')
    badge.alpha_composite(image)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, size - 3, size - 3), fill=255)
    badge.putalpha(mask)
    ImageDraw.Draw(badge).ellipse((2, 2, size - 3, size - 3), outline='#ffffff', width=4)
    return np.asarray(badge)


def probability_label(value):
    if value is None:
        return 'N/A'
    if 0 < value < 1:
        return '<1%'
    if 99 < value < 100:
        return f'{value:.1f}%'
    return f'{value:.0f}%'


def load_rows(csv_path):
    """Probabilities use percentages (0–100); logos are local PNG files."""
    csv_path = Path(csv_path)
    with csv_path.open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        required = {'team', 'current', 'if_loss', 'if_win', 'color'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'CSV must contain: {", ".join(sorted(required))}')
        rows = []
        for line, row in enumerate(reader, start=2):
            if not row['team'].strip():
                raise ValueError(f'Line {line}: team is required')
            for field in ('current', 'if_loss', 'if_win'):
                if field != 'current' and not row[field].strip():
                    row[field] = None
                    continue
                row[field] = float(row[field])
                if not math.isfinite(row[field]) or not 0 <= row[field] <= 100:
                    raise ValueError(f'Line {line}: {field} must be between 0 and 100')
            if not is_color_like(row['color']):
                raise ValueError(f'Line {line}: invalid team color')
            logo = row.get('logo', '').strip()
            candidate = (csv_path.parent / logo).resolve() if logo else None
            row['logo'] = (candidate if candidate and candidate.is_file() and candidate.stat().st_size
                           else find_team_logo(row['team']))
            rows.append(row)
    if not rows:
        raise ValueError('CSV must contain at least one team')
    return sorted(rows, key=lambda row: row['current'], reverse=True)


def render_chart(rows, output, season, week, title='BML Playoff Leverage', note='',
                 probability_name='Playoff', loss_on_right=False, eliminated_teams=(),
                 eliminated_label='Eliminated'):
    """Place each team at its current odds, with tapered conditional ranges."""
    fig, ax = plt.subplots(figsize=(11, max(6, len(rows) * .40 + (3 if title else 2))))
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    ax.set_xlim(-12, 112)
    ax.set_ylim(-3.2, len(rows) + 2.8 if title else len(rows) - .4)
    ax.axis('off')
    if title:
        ax.text(-10, len(rows) + 2, title, fontsize=27, weight='bold', color='#333333')
        ax.text(-10, len(rows) + 1.15, f'{season} season going into week {week}',
                fontsize=17, color='#444444')

    for index, row in enumerate(rows):
        y = len(rows) - index - 1
        current, loss, win = (row[key] for key in ('current', 'if_loss', 'if_win'))
        eliminated = row['team'] in eliminated_teams
        if eliminated:
            current = 0
        color = row['color']
        # Draw each arm independently: conditional sample estimates can cross.
        for endpoint in (() if eliminated else (loss, win)):
            if endpoint is None:
                continue
            ax.add_patch(Polygon([(current, y), (endpoint, y + .14),
                                  (endpoint, y - .14)], color=color, zorder=2))
            ax.scatter([endpoint], [y], s=52, facecolor=BACKGROUND,
                       edgecolor=color, linewidth=1.2, zorder=3)
        # Bootyman risk usually rises after a loss, reversing the playoff layout.
        # Use actual endpoint order so sampling noise cannot put labels inside.
        loss_right = loss_on_right
        if loss is not None and win is not None and loss != win:
            loss_right = loss > win
        endpoints = [current] + [value for value in (loss, win) if value is not None]
        labels = () if eliminated else ((loss, LOSS, loss_right), (win, WIN, not loss_right))
        for value, color, on_right in labels:
            anchor = max(endpoints) if on_right else min(endpoints)
            # Leave space for the circular logo when the range is very narrow.
            padding = 22 if abs(anchor - current) < 3 else 9
            ax.annotate(probability_label(value), (anchor, y),
                        xytext=(padding if on_right else -padding, 0),
                        textcoords='offset points', ha='left' if on_right else 'right',
                        va='center', color=color, fontsize=11, zorder=5)
        if row['logo']:
            pixels = circular_logo(row['logo'])
            marker = OffsetImage(pixels, zoom=32 / pixels.shape[0])
            ax.add_artist(AnnotationBbox(marker, (current, y), frameon=False, zorder=4))
        else:
            ax.scatter([current], [y], s=32 ** 2, facecolor='white',
                       edgecolor=color, linewidth=1.2, zorder=4)
            ax.text(current, y, row['team'][:2].upper(), ha='center', va='center',
                    fontsize=9, weight='bold', color=color, zorder=5)
        if eliminated:
            ax.annotate(eliminated_label, (current, y), xytext=(23, 0),
                        textcoords='offset points', ha='left', va='center',
                        fontsize=11, color='#666666', zorder=5)

    # The legend uses the same geometry as the plotted teams.
    y = -1.8
    for endpoint in (38, 88):
        ax.add_patch(Polygon([(63, y), (endpoint, y + .12),
                              (endpoint, y - .12)], color='#123d68'))
        ax.scatter([endpoint], [y], s=45, facecolor=BACKGROUND, edgecolor='#123d68')
    ax.scatter([63], [y], s=90, color='#123d68', zorder=3)
    loss_x, win_x = (88, 38) if loss_on_right else (38, 88)
    loss_label = f'Bowl Risk After a Loss\nWeek {week}' if loss_on_right else f'% If Loss In\nWeek {week}'
    current_label = 'Current Bowl\nRisk' if loss_on_right else f'Current {probability_name}\nProbability'
    win_label = f'Bowl Risk After a Win\nWeek {week}' if loss_on_right else f'% If Win In\nWeek {week}'
    for x, label, color in ((loss_x, loss_label, LOSS),
                            (63, current_label, '#444444'),
                            (win_x, win_label, WIN)):
        ax.text(x, y + .45, label, ha='center', fontsize=11, weight='bold', color=color)
    if note:
        ax.text(63, -2.7, note, ha='center', va='top', fontsize=10, color='#555555', wrap=True)
    if hasattr(output, 'write'):
        fig.savefig(output, format='png', dpi=200, bbox_inches='tight', facecolor=BACKGROUND)
    else:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=200, bbox_inches='tight', facecolor=BACKGROUND)
    plt.close(fig)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--week', type=int, required=True)
    parser.add_argument('--output', type=Path, default=Path('www/plots/playoff_leverage.png'))
    parser.add_argument('--title', default='BML Playoff Leverage')
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    try:
        rows = load_rows(args.csv)
        output = render_chart(rows, args.output, args.season, args.week, args.title, args.note)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'Saved {output}')


if __name__ == '__main__':
    main()
