import typer, json
from pathlib import Path
from scrape import scrape_hyrox_season, get_latest_hyrox_season

## stand-alone functions for the CLI
def scrape_hyrox_command(
    season_start: int = 1,
    season_end: int | None = None,
    progress_bar: bool = True,
    out_dir: Path = Path('.'),
    overwrite: bool = False,
):
    ## validate the season range
    if season_start < 1:
        raise ValueError("season_start must be an integer greater than 0")

    latest_season = get_latest_hyrox_season()
    if season_end is None:
        season_end = latest_season

    if season_end > latest_season:
        raise ValueError(f"season_end must be less than or equal to the latest season: {latest_season}")

    if season_end < season_start:
        raise ValueError("season_end must be greater than or equal to season_start")

    if season_start > latest_season:
        raise ValueError(f"season_start must be less than or equal to the latest season: {latest_season}")

    ## set the output directory and create it if it doesn't exist
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    if progress_bar:
        from tqdm import tqdm
    else:
        tqdm = lambda x, **kwargs: x

    typer.echo(f"Scraping seasons from {season_start} to {season_end}...")
    seasons = range(season_start, season_end + 1)
    for season in tqdm(list(seasons), desc="Seasons"):
        if not overwrite and (out_dir / f"season-{season}.json").exists():
            continue
        season_dict = scrape_hyrox_season(season, progress_bar=progress_bar, is_outer=False)
        out_path = out_dir / f"season-{season}.json"
        json.dump(season_dict, open(out_path, 'w'), indent=2, ensure_ascii=False)

    print(f"Scraped {len(seasons)} seasons from {season_start} to {season_end}")
    return

##### CLI ########
app = typer.Typer()

@app.command()
def scrape_hyrox(
    season_start: int = typer.Option(1, help="First season number (inclusive). Default is 1."),
    season_end: int = typer.Option(None, help="Last season number (inclusive). Default is the latest season."),
    progress_bar: bool = typer.Option(True, "--progress/--no-progress", help="Show progress bars."),
    out_dir: Path = typer.Option(Path("."), "--out-dir", help="Directory to write JSON files into."),
    overwrite: bool = typer.Option(False, "--overwrite/--no-overwrite", help="Overwrite existing files."),
):
    """
    Examples:

      python cli.py scrape-hyrox --season-start 1 --season-end 3 --out-dir data/
      python cli.py scrape-hyrox --season-start 5 --season-end 5 --no-progress
    """
    scrape_hyrox_command(season_start, season_end, progress_bar, out_dir, overwrite)

if __name__ == "__main__":
    app()