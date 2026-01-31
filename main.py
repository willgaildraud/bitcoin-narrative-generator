#!/usr/bin/env python3
"""The Bitcoin Pulse - CLI Entry Point."""

import argparse
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from config import ANTHROPIC_API_KEY, REPORTS_DIR
from data_fetcher import DataFetcher
from report_generator import ReportGenerator


console = Console()


def ensure_reports_dir():
    """Ensure the reports directory exists."""
    os.makedirs(REPORTS_DIR, exist_ok=True)


def save_report(content: str, output_format: str = "markdown") -> str:
    """Save the report to a file and return the filepath."""
    ensure_reports_dir()

    today = datetime.now().strftime("%Y-%m-%d")
    extension = "html" if output_format == "html" else "md"
    filename = f"btc-report-{today}.{extension}"
    filepath = os.path.join(REPORTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Generate Bitcoin market narrative reports using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  Generate a daily report (Markdown)
  python main.py --weekly         Generate a weekly summary report
  python main.py --output html    Generate report as HTML
  python main.py --weekly --output html  Weekly report as HTML
        """
    )

    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Generate a weekly summary report instead of daily"
    )

    parser.add_argument(
        "--output",
        choices=["markdown", "html"],
        default="markdown",
        help="Output format (default: markdown)"
    )

    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Use template-based generation instead of Claude AI"
    )

    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip historical price fetching for faster generation"
    )

    args = parser.parse_args()

    # Determine if we should use AI
    use_ai = not args.no_ai
    if use_ai and not ANTHROPIC_API_KEY:
        console.print(Panel(
            "[yellow]Note: ANTHROPIC_API_KEY not found.[/yellow]\n\n"
            "Using template-based report generation.\n"
            "To use Claude AI, create a .env file with:\n"
            "[cyan]ANTHROPIC_API_KEY=sk-ant-...[/cyan]",
            title="Configuration Notice"
        ))
        use_ai = False

    report_type = "weekly" if args.weekly else "daily"

    console.print(Panel(
        f"[bold cyan]The Bitcoin Pulse[/bold cyan]\n"
        f"Generating {report_type} report...",
        title="🪙 The Bitcoin Pulse"
    ))

    try:
        # Fetch market data
        console.print("\n[yellow]Step 1/3:[/yellow] Fetching market data...")
        fetcher = DataFetcher()
        data = fetcher.fetch_all_data(include_historical=not args.fast)

        if not data.get("bitcoin"):
            console.print("[red]Error: Failed to fetch Bitcoin data. Please try again later.[/red]")
            sys.exit(1)

        console.print("[green]✓[/green] Market data fetched successfully\n")

        # Generate report
        method = "Claude AI" if use_ai else "templates"
        console.print(f"[yellow]Step 2/3:[/yellow] Generating narrative report with {method}...")
        generator = ReportGenerator(use_ai=use_ai)
        report = generator.generate_report(data, report_type)

        # Convert to HTML if requested
        if args.output == "html":
            report = generator.convert_to_html(report, data)

        console.print("[green]✓[/green] Report generated successfully\n")

        # Save report
        console.print("[yellow]Step 3/3:[/yellow] Saving report...")
        filepath = save_report(report, args.output)
        console.print(f"[green]✓[/green] Report saved to: [cyan]{filepath}[/cyan]\n")

        # Show summary
        bitcoin = data.get("bitcoin", {})
        fear_greed = data.get("fear_greed", {})

        console.print(Panel(
            f"[bold green]Report Generated Successfully![/bold green]\n\n"
            f"[bold]Quick Stats:[/bold]\n"
            f"  • BTC Price: [cyan]${bitcoin.get('price_usd', 0):,.2f}[/cyan]\n"
            f"  • 24h Change: [{'green' if bitcoin.get('price_change_24h_percent', 0) >= 0 else 'red'}]"
            f"{bitcoin.get('price_change_24h_percent', 0):+.2f}%[/]\n"
            f"  • Fear & Greed: [yellow]{fear_greed.get('value', 'N/A')}[/yellow] "
            f"({fear_greed.get('classification', 'N/A')})\n\n"
            f"[dim]Report saved to: {filepath}[/dim]",
            title="✅ Complete"
        ))

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
