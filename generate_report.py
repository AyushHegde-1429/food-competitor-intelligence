import argparse
import html
from pathlib import Path

import database


def build_report_html(report: dict, restaurant: str) -> str:
    price_mismatches = report.get("price_mismatches", [])
    missing_items = report.get("missing_items", [])
    price_changes = report.get("price_changes", [])
    availability_differences = report.get("availability_differences", [])
    summary = report.get("summary", {})

    def list_rows(rows):
        if not rows:
            return "<p>No data available.</p>"
        lines = [
            "<table>",
            "<thead><tr><th>Field</th><th>Value</th></tr></thead>",
            "<tbody>",
        ]
        for row in rows[:10]:
            if isinstance(row, dict):
                cells = []
                for key, value in row.items():
                    cells.append(f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>")
                lines.extend(cells)
        lines.append("</tbody></table>")
        return "\n".join(lines)

    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>{html.escape(restaurant)} report</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
        th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; vertical-align: top; }}
        h1, h2 {{ margin-top: 1.5rem; }}
      </style>
    </head>
    <body>
      <h1>{html.escape(restaurant)} weekly parity report</h1>
      <p><strong>Report date:</strong> {html.escape(str(report.get('report_date', 'n/a')))}</p>
      <h2>Summary</h2>
      {list_rows([summary])}
      <h2>Price mismatches</h2>
      {list_rows(price_mismatches)}
      <h2>Missing items</h2>
      {list_rows(missing_items)}
      <h2>Price changes</h2>
      {list_rows(price_changes)}
      <h2>Availability differences</h2>
      {list_rows(availability_differences)}
      <h2>Limitations</h2>
      <ul>
        {''.join(f'<li>{html.escape(str(item))}</li>' for item in report.get('limitations', []))}
      </ul>
    </body>
    </html>
    """


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a lightweight restaurant parity report.")
    parser.add_argument("--restaurant", required=True, help="Restaurant name to evaluate")
    parser.add_argument("--country", default="UAE")
    parser.add_argument("--city", default="Dubai")
    parser.add_argument("--location", required=True)
    parser.add_argument("--output", default="reports/restaurant_report.html")
    args = parser.parse_args()

    database.create_database()
    report = database.get_restaurant_parity(
        restaurant=args.restaurant,
        country=args.country,
        city=args.city,
        location=args.location,
    )
    report["report_date"] = database._current_timestamp() if hasattr(database, "_current_timestamp") else "n/a"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_report_html(report, args.restaurant), encoding="utf-8")
    print(f"Generated report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
