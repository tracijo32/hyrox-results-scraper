from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from urllib.parse import urlparse, parse_qsl, urlencode

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
    url = f'https://results.hyrox.com/season-{season}'
    if event_main_group:
        query_params = {
            'event_main_group': event_main_group,
            'pid': 'list',
            'pidp': 'ranking_nav',
        }
        url = f'{url}/index.php?{urlencode(query_params)}'
    driver.get(url)

def get_element_once_present(driver, selector: str):
    return WebDriverWait(driver, 10)\
        .until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

def parse_results_pagination(driver) -> int | None:
    '''see if there are links to other pages of results, and if so, return the number of pages'''
    try:
        pagination = driver.find_element(By.CLASS_NAME, 'pagination')
    except:
        return None
    link_tags = pagination.find_elements(By.TAG_NAME, 'a')
    links = [tag.get_attribute('href') for tag in link_tags]

    n_pages = 0
    for link in links:
        parts = urlparse(link)
        q = dict[bytes, bytes](parse_qsl(parts.query, keep_blank_values=True))
        n_pages = max(n_pages, int(q.get('page', 0)))
    return n_pages

def parse_event_id(driver: WebDriver):
    ''' cycle through all links on the page until you find one that has the "event" parameter'''
    current_parts = urlparse(driver.current_url)
    base_url = f"{current_parts.scheme}://{current_parts.netloc}{current_parts.path}"
    all_links = driver.find_elements(By.TAG_NAME, 'a')
    for link in all_links:
        if not link.startswith(base_url):
            continue
        parts = urlparse(link.get_attribute('href'))
        params = dict[bytes, bytes](parse_qsl(parts.query, keep_blank_values=True))
        event = params.get('event')
        if event:
            return event
    return None

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

def get_division_options(driver: WebDriver) -> list[int]:
    '''
    get the division options from the dropdown

    this is a little more complicated than just cycling through the options
    in the select object like we can with other dropdowns because some results
    pages have ALL the options for ALL the events in the season

    To prevent redudant scraping, we have to first find all of the "optgroups", which
    break the division options up by events and then select out the indices of the child
    options that match the event we want.
    '''
    division_dropdown_element = get_element_once_present(driver, '#event')

    option_indices = []
    optgroups = division_dropdown_element.find_elements(By.TAG_NAME, 'optgroup')
    for optgroup in optgroups:
        optgroup_label = optgroup.get_attribute('label')
        for i, _ in enumerate(optgroup.find_elements(By.TAG_NAME, 'option')):
            if optgroup_label == emg:
                option_indices.append(i)
            i += 1
    return option_indices

def get_division_option_indices(driver: WebDriver, event_match_string: str) -> list[int]:
    i = 0
    division_dropdown_element = get_element_once_present(driver, '#event')
    optgroups = division_dropdown_element.find_elements(By.TAG_NAME, 'optgroup')
    for optgroup in optgroups:
        optgroup_label = optgroup.get_attribute('label')
        options = optgroup.find_elements(By.TAG_NAME, 'option')
        if optgroup_label == event_match_string:
            option_indices = [i+j for j in range(len(options))]
            return option_indices
        i += len(options)
    return []

def navigate_to_division(driver: WebDriver, division_index: int):
    '''
    navigate to a specific division and ensure that the results are not filtered 
    by workout or age group we're ranking by total race time and over all age groups
    '''
    division_dropdown = Select(get_element_once_present(driver, '#event'))
    division_dropdown.select_by_index(division_index)

    workout_dropdown = Select(get_element_once_present(driver, '#ranking'))
    workout_dropdown.select_by_visible_text('Total')

    age_group_dropdown = Select(get_element_once_present(driver, '#search\\[age_class\\]'))
    age_group_dropdown.select_by_visible_text('All')
    return