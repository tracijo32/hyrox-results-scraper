from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from urllib.parse import urlparse, parse_qsl, urlencode
import re

## CSS selectors
_event_main_group_selector = '#default-lists-event_main_group'
_division_selector = '#event'
_workout_selector = '#ranking'
_age_group_selector = '#search\\[age_class\\]'
_gender_selector = '#search\\[sex\\]'

## regex patterns
_season_pattern = re.compile(r"/season-(\d+)")
_results_display_pattern = re.compile(r"^Results:\s*(.*?)\s*/\s*(.*)\s*$")

def launch_driver(headless: bool = True, width: int = 1800, height: int = 800) -> WebDriver:
    """launch the selenium Chrome driver"""
    ## Automatically downloads the correct chromedriver version and returns its path
    service = Service(ChromeDriverManager().install())

    ## set driver options
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")

    ## Initialize the Chrome browser instance using the automatically managed driver
    driver = webdriver.Chrome(service=service, options=options)
    return driver   

def navigate_to_results(driver, season: int, event_main_group: str | None = None):
    if season < 1:
        raise ValueError(f"season must be an integer greater than 0")

    ## if we don't know any of the events in the season, we can pull them from page that
    ## builds the query, otherwise, we can put the event_main_group in the query and go to the
    ## straight to the results page
    base_url = 'https://results.hyrox.com'
    path_url = f'{base_url}/season-{season}'
    if event_main_group:
        query_params = {
            'event_main_group': event_main_group,
            'pid': 'list',
            'pidp': 'ranking_nav',
        }
        url = f'{path_url}/index.php?{urlencode(query_params)}'
        selector_to_wait_for = _division_selector
    else:
        url = path_url
        selector_to_wait_for = _event_main_group_selector

    driver.get(url)
    get_element_once_present(driver, selector_to_wait_for)

    ## if the season we entered is out of range, it will redirect to the latest season
    ## we can check that the paths match to make sure we're on the right page
    if not driver.current_url.startswith(path_url):
        raise ValueError(f"Invalid season url: {driver.current_url}")

    ## another way to validate that we're on the right page is to parse the season number
    ## from the title of the results page
    number, _ = parse_season(driver)
    if number != season:
        raise ValueError(f"Season mismatch: {number} != {season}")

    ## unfortunately, this is not a foolproof way to validate that we're on the right page
    ## because the event_main_group is not always present in the query params
    ## so we also check the display name of the event main group
    ## that also doesn't really work: if an invalid event main group is entered,
    ## then the results page will just be empty
    parts = urlparse(driver.current_url)
    q = dict[str, str](parse_qsl(parts.query))
    if q.get('event_main_group') != event_main_group:
        raise ValueError(f"Event main group mismatch: {q.get('event_main_group')} != {event_main_group}")
    if event_main_group:
        emg_display, _ = parse_results_display(driver)
        if emg_display != event_main_group:
            raise ValueError(f"Event main group mismatch: {emg_display} != {event_main_group}")
    return

def get_element_once_present(driver, selector: str):
    return WebDriverWait(driver, 2)\
        .until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

def parse_leaderboard(driver: WebDriver):
    leaderboard = driver.find_element(By.CLASS_NAME, 'list-group-multicolumn')
    header = leaderboard.find_element(By.CLASS_NAME, 'list-group-header')

    column_names = []
    for column in header.find_elements(By.CLASS_NAME, 'list-field'):
        if 'place-primary' in column.get_attribute('class'):
            col_text = 'rank_primary'
        elif 'place-secondary' in column.get_attribute('class'):
            col_text = 'rank_secondary'
        elif column.text.startswith('Nat'):
            col_text = 'nationality'
        else:
            col_text = column.text.lower().replace(' ', '_')
        column_names.append(col_text)
        
    leaderboard_data = []
    rows = leaderboard.find_elements(By.CLASS_NAME, 'list-group-item')
    for row in rows:
        if 'list-group-header' in row.get_attribute('class'):
            continue
        values = {c:t for c, t in zip(column_names, row.text.split('\n'))}
        link_to_details = row.find_element(By.TAG_NAME, 'a').get_attribute('href')
        parts = urlparse(link_to_details)
        q = dict[bytes, bytes](parse_qsl(parts.query, keep_blank_values=True))
        values['event'] = q['event']
        values['idp'] = q['idp']
        leaderboard_data.append(values)
    return leaderboard_data

def parse_season(driver: WebDriver):
    switcher = driver.find_element(By.CLASS_NAME, 'view-switcher')
    name = switcher.text
    link = switcher.find_element(By.TAG_NAME, 'a').get_attribute('href')
    number = int(re.search(r"/season-(\d+)", link).group(1))
    return number, name

def parse_results_display(driver: WebDriver) -> tuple[str, str]:
    title_element = get_element_once_present(driver, '#cbox-main > div:nth-child(1)')
    m = _results_display_pattern.match(title_element.text)
    if not m:
        raise ValueError(f"Unrecognized format: {title_element.text}")
    event_name = m.group(1)
    division_name = m.group(2)
    return event_name, division_name

def parse_event_id(driver: WebDriver):
    ''' cycle through all links on the page until you find one that has the "event" parameter'''
    current_parts = urlparse(driver.current_url)
    base_url = f"{current_parts.scheme}://{current_parts.netloc}{current_parts.path}"
    all_links = [link.get_attribute('href') for link in driver.find_elements(By.TAG_NAME, 'a')]
    for link in all_links:
        if not link.startswith(base_url):
            continue
        parts = urlparse(link)
        params = dict[bytes, bytes](parse_qsl(parts.query, keep_blank_values=True))
        event = params.get('event')
        if event:
            return event
    return None

def get_dropdown(driver: WebDriver, selector: str):
    return Select(get_element_once_present(driver, selector))

def get_division_options(driver: WebDriver, event_match_string: str) -> dict[int, str]:
    '''
    get the division options from the dropdown

    this is a little more complicated than just cycling through the options
    in the select object like we can with other dropdowns because some results
    pages have ALL the options for ALL the events in the season

    To prevent redudant scraping, we have to first find all of the "optgroups", which
    break the division options up by events and then select out the indices of the child
    options that match the event we want.
    '''
    i = 0
    division_dropdown_element = get_element_once_present(driver, '#event')
    optgroups = division_dropdown_element.find_elements(By.TAG_NAME, 'optgroup')
    for optgroup in optgroups:
        optgroup_label = optgroup.get_attribute('label')
        options = optgroup.find_elements(By.TAG_NAME, 'option')
        if optgroup_label == event_match_string:
            option_indices = {i+j:opt.text for j, opt in enumerate(options)}
            return option_indices
        i += len(options)
    return {}

_event_main_group_selector = '#default-lists-event_main_group'
_division_selector = '#event'
_workout_selector = '#ranking'
_age_group_selector = '#search\\[age_class\\]'
_gender_selector = '#search\\[sex\\]'

def select_results_from_dropdowns(
    driver: WebDriver, 
    division_index: int = 0, 
    gender_index: int | None = None
):
    '''
    navigate to a specific division and ensure that the results are not filtered 
    by workout or age group we're ranking by total race time and over all age groups
    '''
    division_dropdown = get_dropdown(driver, _division_selector)
    division_dropdown.select_by_index(division_index)

    workout_dropdown = get_dropdown(driver, _workout_selector)
    workout_dropdown.select_by_visible_text('Total')

    age_group_dropdown = get_dropdown(driver, _age_group_selector)
    age_group_dropdown.select_by_visible_text('All')

    if gender_index is not None:
        gender_dropdown = get_dropdown(driver, _gender_selector)
        gender_dropdown.select_by_index(gender_index)
    return

def get_gender_options(driver: WebDriver) -> dict[int, str]:
    try:
        gender_dropdown = get_dropdown(driver, _gender_selector)
        return {i: opt.text for i, opt in enumerate(gender_dropdown.options)}
    except TimeoutException:
        return {}

def parse_pagination(driver: WebDriver) -> int:
    '''
    Returns the number of pages of results available.
    '''
    ## first check if there the alert box pops up that says
    ## "There are currently no results available."
    ## if so, there are no results and we exit
    try:
        driver.find_element(By.CLASS_NAME, 'alert')
        return 0
    except:
        pass

    ## if there is no alert box, then check if there's a pagination bar
    ## if there isn't one, then theres only one page
    try:
        pagination = driver.find_element(By.CLASS_NAME, 'pagination')
    except:
        return 1

    ## find the link to the last page (max page number)
    link_tags = pagination.find_elements(By.TAG_NAME, 'a')
    links = [tag.get_attribute('href') for tag in link_tags]

    n_pages = 1
    for link in links:
        parts = urlparse(link)
        q = dict[bytes, bytes](parse_qsl(parts.query, keep_blank_values=True))
        n_pages = max(n_pages, int(q.get('page', 1)))
    return n_pages

def get_latest_hyrox_season():
    driver = launch_driver()
    driver.get('https://results.hyrox.com')
    number, _ = parse_season(driver)
    driver.close()
    return number

def scrape_hyrox_season(season: int, progress_bar: bool = True, is_outer: bool = False):
    if progress_bar:
        from tqdm import tqdm
    else:
        tqdm = lambda x, **kwargs: x

    if season < 1:
        raise ValueError(f"season must be an integer greater than 0")

    driver = launch_driver()
    navigate_to_results(driver, season)
    number, name = parse_season(driver)
    if number != season:
        raise ValueError(f"Season mismatch: {number} != {season}")

    season_dict = {
        'season': season,
        'name': name,
        'events': []
    }

    main_dropdown = Select(get_element_once_present(driver, _event_main_group_selector))
    event_main_groups = {i: opt.text for i, opt in enumerate(main_dropdown.options)}

    for i, emg in tqdm(
        event_main_groups.items(),
        total=len(event_main_groups),
        leave=is_outer,
        desc='Events'
    ):
        navigate_to_results(driver, season, emg)
        event_dict = {
            'event_index': i,
            'event_main_group': emg,
            'event_id': parse_event_id(driver),
            'divisions': []
        }

        division_options = get_division_options(driver, emg)
        for j, div in tqdm(division_options.items(), leave=False, desc='Divisions'):
            try:
                select_results_from_dropdowns(driver, j)
                event_display_name, division_display_name = parse_results_display(driver)
                division_dict = {
                    'division_index': j,
                    'division_name': div,
                    'event_display_name': event_display_name,
                    'division_display_name': division_display_name,
                    'genders': []
                }
                gender_options = get_gender_options(driver)
                for k, gdr in gender_options.items():
                    try:
                        select_results_from_dropdowns(driver, j, k)
                        gender_dict = {
                            'gender_index': k,
                            'gender': gdr,
                            'n_pages': parse_pagination(driver)
                        }
                    except Exception as e:
                        gender_dict = {'error': str(e)}
                    division_dict['genders'].append(gender_dict)
            except Exception as e:
                division_dict = {'error': str(e)}
            event_dict['divisions'].append(division_dict)
        season_dict['events'].append(event_dict)
    driver.quit()
    return season_dict
    