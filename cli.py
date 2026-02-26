import typer, json, traceback
from tqdm import tqdm
from pathlib import Path
from scrape import (
    scrape_hyrox_season, 
    get_latest_hyrox_season, 
    scrape_leaderboard,
    launch_driver,
    _log_error
)

## stand-alone functions for the CLI
def scrape_divisions_command(
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

def clean_data(seasons: dict):
    records = [
        {
            'season': season['season'],
            'event_id': division['event_id'],
            'event_main_group': event['event_main_group'],
            'division_name': division['division_name'],
            'gender': gender['gender'],
            'sex': 'X' if gender['gender'].lower() == 'mixed' else gender['gender'][0].upper(),
            'n_pages': gender['n_pages']
        }
        for season in seasons
        for event in season['events']
        for division in event['divisions']
        for gender in division['genders']
        if gender.get('n_pages',0) > 0
    ]
    return records

def form_file_path(season: int, event: str, sex: str, **kwargs):
    from pathlib import Path
    dirs = Path(
        f'season={season}',
        f'event={event}',
        f'sex={sex}'
    )
    return dirs

def scrape_leaderboards_command(
    in_dir: Path = Path('.'), 
    out_dir: Path = Path('.'),
    overwrite: bool = False,
):
    import glob
    in_dir = Path(in_dir).expanduser()
    season_files = glob.glob(str(in_dir / 'season-*.json'))
    seasons = [json.load(open(file)) for file in season_files]

    ## set the output directory and create it if it doesn't exist
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    ## cleaned the records to only events and divsions with actual results
    records = clean_data(seasons)

    ## reformat the records: add sex code from gender, add file path
    ##change 'event_id' to 'event' for consistency with url parameters
    records = [{('event' if k == 'event_id' else k): v for k, v in record.items()} for record in records]
    records = [
        {
            'sex': 'X' if record['gender'].lower() == 'mixed' else record['gender'][0].upper(),
            'file_path': form_file_path(**record),
            **record
        }
        for record in records
    ]
    ## before we do any scraping, we need to check if the files already exist and skip them if they do
    ## unless we're overwriting them
    total_records = len(records)
    if overwrite:
        completed = 0
    else:
        existing_files = glob.glob(str(out_dir / '**' / '*.json'))
        records = [
            record for record in records
            if str(record['file_path']) not in existing_files
        ]
        completed = total_records - len(records)
        typer.echo(f"Skipping {completed} records that already exist")
    
    ## scrape the leaderboards: loop through the records and scrape the leaderboard for each page
    driver = launch_driver()
    try:
        with tqdm(total=total_records, desc="Scraping leaderboards", initial=completed) as pbar:
            for record in records:
                lb_path = out_dir / form_file_path(**record)
                lb_path.mkdir(parents=True, exist_ok=True)
                for page in range(1, record['n_pages'] + 1):
                    file_path = lb_path / f'page={page}.json'
                    if file_path.exists() and not overwrite:
                        continue
                    try:   
                        lb_data = scrape_leaderboard(driver, page=page, **record)
                    except Exception as e:
                        lb_data = _log_error(e)

                    out = {
                        k: v for k, v in record.items() if k not in ['file_path', 'sex']
                    }
                    out['current_page'] = page
                    out['leaderboard'] = lb_data

                    with open(file_path, 'w') as f:
                        json.dump(lb_data, f)
                pbar.update(1)
        typer.echo(f"Scraped {len(records)} leaderboards")
    except Exception as e:
        raise e
    finally:
        driver.quit()

    return

##### CLI ########
app = typer.Typer()

@app.command()
def scrape_divisions(
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
    scrape_divisions(season_start, season_end, progress_bar, out_dir, overwrite)

@app.command()
def scrape_leaderboards(
    in_dir: Path = typer.Option(Path("."), "--in-dir", help="Directory to read season-*.json files from."),
    out_dir: Path = typer.Option(Path("."), "--out-dir", help="Directory to write JSON files into."),
    overwrite: bool = typer.Option(False, "--overwrite/--no-overwrite", help="Overwrite existing files."),
):
    scrape_leaderboards_command(in_dir, out_dir, overwrite)

if __name__ == "__main__":
    app()