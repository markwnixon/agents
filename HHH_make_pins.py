import os
import sys

import socket
from utils import getpaths

import time
from datetime import datetime, timedelta
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(__file__), ".ms-playwright"))
try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The Playwright Python package is not installed. Install it in the "
        "flaskenv venv with: pip install playwright && playwright install chromium"
    ) from exc
from utils import hasinput


class TimeoutException(Exception):
    pass


class StaleElementReferenceException(Exception):
    pass


class By:
    ID = "id"
    XPATH = "xpath"
    TAG_NAME = "tag_name"


def _selector(by, value):
    if by == By.ID:
        return f"#{value}"
    if by == By.XPATH:
        return f"xpath={value}"
    if by == By.TAG_NAME:
        return value
    return value


class PlaywrightElement:
    def __init__(self, locator):
        self.locator = locator

    @property
    def text(self):
        try:
            return self.locator.inner_text(timeout=1000).strip()
        except PlaywrightTimeoutError:
            text = self.locator.text_content(timeout=1000)
            return text.strip() if text else ""

    def is_displayed(self):
        try:
            return self.locator.is_visible(timeout=500)
        except PlaywrightTimeoutError:
            return False

    def clear(self):
        self.locator.fill("")

    def send_keys(self, text):
        self.locator.fill(str(text))

    def submit(self):
        self.locator.press("Enter")

    def click(self):
        self.locator.click()

    def is_checked(self):
        try:
            return self.locator.is_checked(timeout=500)
        except PlaywrightTimeoutError:
            return False

    def find_elements(self, by, value):
        locator = self.locator.locator(_selector(by, value))
        return [PlaywrightElement(locator.nth(i)) for i in range(locator.count())]


class PlaywrightPage:
    def __init__(self, playwright, browser, page):
        self._playwright = playwright
        self._browser = browser
        self._page = page

    @property
    def current_url(self):
        return self._page.url

    def maximize_window(self):
        self._page.set_viewport_size({"width": 1920, "height": 1200})

    def get(self, url):
        current_base = self._page.url.split("#")[0]
        target_base = url.split("#")[0]
        hash_route = "#" in url and current_base == target_base
        if "#" in url and current_base == target_base:
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                self._page.evaluate("url => { window.location.href = url; }", url)
                self._page.wait_for_timeout(250)
            except PlaywrightError:
                self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        else:
            self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            self._page.wait_for_load_state("networkidle", timeout=2000 if hash_route else 5000)
        except PlaywrightTimeoutError:
            pass

    def quit(self):
        self._browser.close()
        self._playwright.stop()

    def find_element(self, by, value):
        locator = self._page.locator(_selector(by, value)).first
        locator.wait_for(state="attached", timeout=5000)
        return PlaywrightElement(locator)

    def find_element_by_xpath(self, xpath):
        return self.find_element(By.XPATH, xpath)

    def find_elements(self, by, value):
        locator = self._page.locator(_selector(by, value))
        return [PlaywrightElement(locator.nth(i)) for i in range(locator.count())]

    def find_elements_by_xpath(self, xpath):
        return self.find_elements(By.XPATH, xpath)

    def execute_script(self, script, *args):
        if "arguments[0].click()" in script and args:
            args[0].locator.click(force=True)
            return None
        if "scrollIntoView" in script and args:
            args[0].locator.scroll_into_view_if_needed(timeout=5000)
            return None
        handles = [arg.locator.element_handle(timeout=5000) if isinstance(arg, PlaywrightElement) else arg for arg in args]
        return self._page.evaluate(f"(args) => {{ {script} }}", handles)

    def visible_xpath(self, xpath, timeout=5000):
        locator = self._page.locator(f"xpath={xpath}").first
        locator.wait_for(state="visible", timeout=timeout)
        return PlaywrightElement(locator)

    def attached_xpath(self, xpath, timeout=5000):
        locator = self._page.locator(f"xpath={xpath}").first
        locator.wait_for(state="attached", timeout=timeout)
        return PlaywrightElement(locator)

    def click_text(self, text, timeout=5000):
        locator = self._page.get_by_text(text, exact=True).first
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()

    def page_has_text(self, text):
        try:
            return self._page.get_by_text(text).first.is_visible(timeout=500)
        except PlaywrightTimeoutError:
            return False

    def press_enter(self):
        self._page.keyboard.press("Enter")


class WebDriverWait:
    def __init__(self, browser, timeout, poll_frequency=0.5):
        self.browser = browser
        self.timeout = timeout
        self.poll_frequency = poll_frequency

    def until(self, condition):
        end_time = time.time() + self.timeout
        last_error = None
        while time.time() < end_time:
            try:
                value = condition(self.browser)
                if value:
                    return value
            except Exception as exc:
                last_error = exc
            time.sleep(self.poll_frequency)
        raise TimeoutException(str(last_error) if last_error else "Timed out waiting for condition")


class EC:
    @staticmethod
    def presence_of_element_located(locator_tuple):
        by, value = locator_tuple

        def _predicate(browser):
            elements = browser.find_elements(by, value)
            return elements[0] if elements else False

        return _predicate

    @staticmethod
    def visibility_of_element_located(locator_tuple):
        by, value = locator_tuple

        def _predicate(browser):
            for element in browser.find_elements(by, value):
                if element.is_displayed():
                    return element
            return False

        return _predicate

    @staticmethod
    def element_to_be_clickable(locator_tuple):
        by, value = locator_tuple

        def _predicate(browser):
            for element in browser.find_elements(by, value):
                try:
                    if element.is_displayed() and element.locator.is_enabled(timeout=500):
                        return element
                except PlaywrightTimeoutError:
                    pass
            return False

        return _predicate


class Select:
    def __init__(self, element):
        self.element = element

    @property
    def options(self):
        locator = self.element.locator.locator("option")
        return [PlaywrightElement(locator.nth(i)) for i in range(locator.count())]

    def select_by_index(self, index):
        value = self.options[index].locator.get_attribute("value")
        self.element.locator.select_option(value=value)

    def select_by_value(self, value):
        self.element.locator.select_option(value=value)


class ActionChains:
    def __init__(self, browser):
        self.browser = browser
        self._element = None
        self._keys = None

    def move_to_element(self, element):
        self._element = element
        return self

    def pause(self, seconds):
        time.sleep(seconds)
        return self

    def click(self):
        if self._element:
            self._element.locator.click(force=True)
        return self

    def send_keys(self, text):
        self._keys = text
        return self

    def perform(self):
        if self._keys is not None:
            if self._element:
                self._element.locator.select_option(label=self._keys)
            else:
                self.browser._page.keyboard.type(str(self._keys))
        self._keys = None
        return self


def launch_browser():
    playwright = sync_playwright().start()
    headless = os.environ.get("GPIN_HEADLESS", "0").lower() in ("1", "true", "yes")
    browser = playwright.chromium.launch(
        headless=headless,
        chromium_sandbox=False,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-seccomp-filter-sandbox",
            "--window-size=1920,1200",
        ],
    )
    context = browser.new_context(viewport={"width": 1920, "height": 1200})
    page = context.new_page()
    return PlaywrightPage(playwright, browser, page)

try:
    scac = sys.argv[1]
    nt = 'remote'
    print(f'Received input argument of SCAC: {scac}')
except:
    print('Must have a SCAC code argument or will get from setup file')
    print('Setting SCAC to FELA since none provided')
    scac = 'fela'
    nt = 'remote'

scac = scac.upper()

if scac == 'OSLM' or scac == 'FELA' or scac == 'NEVO':
    print(f'Running HHH_make_pins for {scac} in tunnel mode: {nt}')

    host_name = socket.gethostname()
    print("Host Name:", host_name)
    dropbox_path = getpaths(host_name, 'dropbox')
    ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
    sys_path = getpaths(host_name, 'system')
    sys.path.append(sys_path) #So we can import CCC_system_setup from full path

    os.environ['SCAC'] = scac
    os.environ['PURPOSE'] = 'script'
    os.environ['MACHINE'] = host_name
    os.environ['TUNNEL'] = nt

    from remote_db_connect import db
    if nt == 'remote': from remote_db_connect import tunnel
    from models8 import Interchange, Orders, Drivers, Pins
    from CCC_system_setup import websites, usernames, passwords

else:
    scac = 'nogo'
    print('The argument must be FELA or OSLM or NEVO')
    quit()


printif = 0

runat = datetime.now()
tnow = runat.strftime("%M")
mins = int(tnow)
today = runat.date()
print(' ')
print('_______________________________________________________')
print(f'This sequence run date: {today}')
print('_______________________________________________________')
print(' ')
textblock = f'This sequence run at {runat} and minutes are {mins}\n'

def closethepopup(browser, close_button_xpath, timeout=10):
    wait = WebDriverWait(browser, timeout)

    wait.until(EC.presence_of_element_located((By.XPATH, close_button_xpath)))

    for _ in range(3):
        try:
            for btn in browser.find_elements(By.XPATH, close_button_xpath):
                if btn.is_displayed() and "close" in btn.text.lower():
                    browser.execute_script("arguments[0].click();", btn)
                    return True
        except StaleElementReferenceException:
            pass

    return False

def softwait(browser, xpath, timeout=16):
    try:
        wait = WebDriverWait(browser, timeout, poll_frequency=0.5)
        return wait.until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        print(f"Timed out waiting for element: {xpath}")
        return None

def softwait_long(browser, xpath, timeout=30):
    """
    Waits for a toast/message to become visible again.
    Works for repeated PrimeFaces-style messages.
    """
    end_time = time.time() + timeout

    while time.time() < end_time:
        elements = browser.find_elements(By.XPATH, xpath)
        for el in elements:
            if el.is_displayed() and el.text.strip():
                return el
        time.sleep(0.25)

    print("Timeout waiting for toast to reappear")
    return None

def hard_select_option(browser, select_id, option_text, timeout=20, retries=3):
    """
    Performs a 'hard' selection on a select box:
    - clicks into the select
    - sends keys for the option
    - triggers SPA JS
    Retries if element is stale.
    """
    for attempt in range(retries):
        try:
            # Wait until the select element is clickable
            selectElem = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((By.ID, select_id))
            )

            # Scroll into view (headless mode may need this)
            browser.execute_script("arguments[0].scrollIntoView({block:'center'});", selectElem)

            # Perform hard selection
            action = ActionChains(browser)
            action.move_to_element(selectElem).click().perform()
            time.sleep(0.1)  # tiny pause to ensure focus
            action.send_keys(option_text).perform()

            return

        except StaleElementReferenceException:
            # Element was replaced by JS, retry
            time.sleep(0.2)
        except TimeoutException:
            time.sleep(0.2)

    raise Exception(f"Failed to hard-select '{option_text}' in select '{select_id}'")

def fill_input_and_verify(browser, by, value, text, label, timeout=20, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            elem = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            browser.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            elem.locator.click()
            elem.clear()
            elem.locator.type(str(text), delay=20)
            WebDriverWait(browser, 5, poll_frequency=0.2).until(
                lambda d: elem.locator.input_value(timeout=500) == str(text)
            )
            return elem
        except Exception as exc:
            last_error = exc
            print(f'{label} input fill verification failed on try {attempt}; retrying', flush=True)
            time.sleep(0.5)
    raise TimeoutException(f"Could not verify {label} input value: {last_error}")

def get_text(browser, xpath):
    time.sleep(1)
    textboxes = browser.find_elements_by_xpath(xpath)
    # if textboxes = []
    time.sleep(1)
    print(f'The textboxes for xpath {xpath} is {textboxes}')
    ret_text = 'xxxxx'
    if textboxes:
        for textbox in textboxes:
            thistext = textbox.text
            print(f'Finding textboxes on page: {thistext}')
            if 'Pre-Advise PIN' in thistext: ret_text = thistext
    else:
        ret_text = 'No textboxes found'
    return ret_text

def get_result_message(browser, timeout=15):
    """
    Returns success PIN message or error dialog text.
    """
    error = 0

    wait = WebDriverWait(browser, timeout)

    # XPaths
    success_xpath = "//*[contains(text(),'Pre-Advise created successfully')]"
    error_xpath = "//div[contains(@class,'ui-dialog-content')]//td[contains(@class,'error')]"
    # NEW: alert dialog without td.error
    alert_xpath = "//div[@id='dialog-alert']//td[normalize-space()]"

    try:
        elem = wait.until(
            lambda d: next(
                (
                    e for e in
                    d.find_elements(By.XPATH, success_xpath)
                    + d.find_elements(By.XPATH, error_xpath)
                    + d.find_elements(By.XPATH, alert_xpath)
                    if e.is_displayed() and e.text.strip()
                ),
                None
            )
        )

        text = elem.text.strip()
        print(f"Popup message found: {text}")

        if 'successfully' in text:
            error = False
        else: error = True

        return text, error

    except TimeoutException:
        debug_visible_messages(browser)
        return "No result message found", True

# Wait until the select has more than 1 option (skip placeholder 'Loading...')
def wait_for_timeslots(browser, xpath, timeout=20):

    def options_populated(driver):
        sel = driver.find_element(By.XPATH, xpath)
        return len(sel.find_elements(By.TAG_NAME, "option")) > 1  # >1 to skip placeholder

    return WebDriverWait(browser, timeout).until(options_populated)

def fillapptdata(browser, d, p, thisdate):
    softwait(browser, '//*[@id="DualInfo_NewApptDate"]')
    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_NewApptDate"]')
    selectElem.send_keys(thisdate)
    selectElem.submit()
    #time.sleep(3)

    timedata = ['06:00-07:00', '07:00-08:00', '08:00-09:00', '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                '13:00-14:00', '14:00-15:00', '15:00-16:30', '15:00-17:30', '15:00-16:00']

    #softwait(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    wait_for_timeslots(browser, '//*[@id="DualInfo_NewTimeSlotKey"]')
    selectElem = Select(browser.find_element_by_xpath('//*[@id="DualInfo_NewTimeSlotKey"]'))
    #time.sleep(1)
    itime = p.Timeslot
    timeslotname = None

    sitems = selectElem.options
    sopts = len(sitems)
    timevec = []
    for i in sitems:
        timevec.append(i.text)
    print(f'We are looking for time slot {itime} in the vector of available times: {timevec}')

    for ix, td in enumerate(timevec):
        if itime in td:
            print(f'We have found timeslot {itime} in the the time available of: {td}')
            timeslotname = td
            iselect = ix

    if timeslotname is None:
            print('We have no matching timeslots, go to next available timeslot that IS available')
            for ix, td in enumerate(timedata):
                if itime in td:
                    for kx in range(ix+1, len(timedata)+1):
                        nexttimeslot = timedata[kx]
                        for jx, td in enumerate(timevec):
                            if nexttimeslot in td:
                                print(f'Need to adjust from timeslot {itime} to timeslot {nexttimeslot}')
                                timeslotname = td
                                iselect = jx
                                break
                        if timeslotname is not None: break
                if timeslotname is not None: break


    selectElem.select_by_index(iselect)

    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_LicensePlateNumber"]')
    selectElem.send_keys(p.Tag)
    selectElem = browser.find_element_by_xpath('//*[@id="DualInfo_DriverMobileNumber"]')
    selectElem.send_keys(d.Phone)
    ret_text = f'Pin made for {p.Driver} in Unit {p.Unit} time slot {timeslotname} chassis {p.InChas}'
    return ret_text


def wait_for_booking_result(browser, timeout=5):
    BOOKING_NOT_FOUND_XPATH = (
        "//div[@id='divBookingSummary']//td[normalize-space()='Booking was not found']"
    )

    PAST_BOOKING_XPATH = (
        "//div[@id='divBookingSummary']//td[normalize-space()='Past Booking']"
    )

    BOOKING_FULL_XPATH = (
        "//span[contains(@class,'error') and "
        "contains(normalize-space(),'All appointments have been made')]"
    )

    CHASSIS_XPATH = (
        "//*[@id='EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber']"
    )

    ALL_IS_WELL_XPATH = (
        "//*[@id='FullInAppts_0__ContainerNumber']"
    )

    wait = WebDriverWait(browser, timeout)

    try:
        wait.until(
            lambda d: (
                    d.find_elements(By.XPATH, BOOKING_NOT_FOUND_XPATH)
                    or d.find_elements(By.XPATH, BOOKING_FULL_XPATH)
                    or d.find_elements(By.XPATH, PAST_BOOKING_XPATH)
                    or d.find_elements(By.XPATH, CHASSIS_XPATH)
                    or d.find_elements(By.XPATH, ALL_IS_WELL_XPATH)
            )
        )
    except TimeoutException:
        debug_visible_messages(browser)
        return "No booking result found after entering booking", True

    # ❌ Booking not found
    err = browser.find_elements(By.XPATH, BOOKING_NOT_FOUND_XPATH)
    if err:
        return err[0].text.strip(), True

    err = browser.find_elements(By.XPATH, PAST_BOOKING_XPATH)
    if err:
        return err[0].text.strip(), True

    # ❌ Booking full
    err = browser.find_elements(By.XPATH, BOOKING_FULL_XPATH)
    if err:
        return err[0].text.strip(), True

    # ✅ Success path, or if time out looking for an error
    return 'continue', False


def wait_for_container_result(browser, timeout=15):
    # This function checks to see if the container associated with a pin reservation is allowed to be pulled
    # from the port and if it is not it returns the error messages.  If no error it allow continuation
    # INLINE_ERROR_XPATH = (
    #    "//span[contains(@class,'error') and "
    #    "contains(text(),'Unable to create pre-advise')]"
    # )
    ERROR_SPANS_XPATH = "//*[contains(@class,'error')]"

    # The element that only appears if container is accepted
    PIN_XPATH = "//*[@id='ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber']"
    #'//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]'
    wait = WebDriverWait(browser, timeout)

    elems = wait.until(
        lambda d: (
                d.find_elements(By.XPATH, ERROR_SPANS_XPATH)
                or d.find_elements(By.XPATH, PIN_XPATH)
        )
    )
    # Check for errors first
    error_spans = browser.find_elements(By.XPATH, ERROR_SPANS_XPATH)
    if error_spans:
        msg = " ".join(
            s.text.strip()
            for s in error_spans
            if s.text.strip()
        )
        return msg, True

    # Otherwise success
    return 'continue', False

def appointment_url_from(current_url):
    base_url = current_url.split('#')[0]
    return f"{base_url}#/appointment/LimitedPreAdvise"

def try_new_preadvise_menu(browser):
    page = browser._page
    for label in ("Pre-Advise", "New Pre-Advise"):
        clicked = False
        candidates = [
            page.get_by_text(label, exact=True),
            page.locator(f"text={label}"),
            page.locator(f"a:has-text('{label}')"),
            page.locator(f"button:has-text('{label}')"),
            page.locator(f"li:has-text('{label}')"),
            page.locator(f"xpath=//*[normalize-space()='{label}']"),
            page.locator(f"xpath=//*[contains(normalize-space(),'{label}')]"),
        ]
        for locator in candidates:
            try:
                element = locator.first
                element.wait_for(state="visible", timeout=5000)
                element.hover()
                time.sleep(0.5)
                element.click()
                clicked = True
                time.sleep(1)
                break
            except PlaywrightTimeoutError:
                continue
            except Exception:
                try:
                    element.click(force=True)
                    clicked = True
                    time.sleep(1)
                    break
                except Exception:
                    continue
        if not clicked:
            print(f'Could not find visible menu label: {label}', flush=True)
            return False

    return True

def commit_field_without_enter(locator):
    locator.dispatch_event("input")
    locator.dispatch_event("change")
    locator.evaluate("el => el.blur()")
    time.sleep(0.5)

def wait_for_ssco_populated(browser, ssco_xpath=None, panel_xpath=None, timeout=20):
    page = browser._page
    selectors = []
    if ssco_xpath:
        selectors.append(f"xpath={ssco_xpath}")
    if panel_xpath:
        selectors.extend([
            f"xpath={panel_xpath}//select[contains(@id,'SscoCode')]",
            f"xpath={panel_xpath}//select[@data-name='dual-ssco']",
        ])
    if not selectors:
        selectors.extend([
            "xpath=//select[contains(@id,'ContainerAppts') and contains(@id,'SscoCode')]",
            "xpath=//select[contains(@id,'EmptyInAppts') and contains(@id,'SscoCode')]",
        ])

    deadline = time.time() + timeout
    last_seen = ""
    while time.time() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="attached", timeout=500)
                value = clean_ssco_value(locator.input_value(timeout=500))
                text = clean_ssco_value(
                    locator.locator("option:checked").first.text_content(timeout=500)
                )
                last_seen = value or text or last_seen
                if value and value.lower() != "select":
                    print(f'SSCO populated: {value}', flush=True)
                    return value
                if text and text.lower() != "select":
                    print(f'SSCO populated: {text}', flush=True)
                    return text
            except Exception:
                continue
        time.sleep(0.25)

    raise TimeoutException(f"Timed out waiting for SSCO to populate; last value was '{last_seen}'")

def clean_ssco_value(value):
    return str(value or "").strip()

def first_visible_enabled(locator, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for ix in range(locator.count()):
                item = locator.nth(ix)
                if item.is_visible(timeout=250) and item.is_enabled(timeout=250):
                    return item
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutException("Timed out waiting for visible enabled locator")

def debug_locator_state(page, name, selector):
    try:
        locator = page.locator(selector)
        count = locator.count()
        visible = locator.first.is_visible(timeout=500) if count else False
        enabled = locator.first.is_enabled(timeout=500) if count else False
        value = ""
        if count:
            try:
                value = clean_ssco_value(locator.first.input_value(timeout=500))
            except Exception:
                value = clean_ssco_value(locator.first.text_content(timeout=500))
        print(f'  {name}: count={count} visible={visible} enabled={enabled} value="{value}"', flush=True)
    except Exception as exc:
        print(f'  {name}: debug failed: {exc}', flush=True)

def debug_paired_move_state(browser, label, intype=None, outtype=None):
    page = browser._page
    print(f'DEBUG paired move state - {label}', flush=True)
    debug_locator_state(page, 'IsInMove', '#IsInMove')
    debug_locator_state(page, 'IsOutMove', '#IsOutMove')
    debug_locator_state(page, 'PrimaryMoveType', '#PrimaryMoveType')
    try:
        primary_text = clean_ssco_value(page.locator("#PrimaryMoveType option:checked").first.text_content(timeout=500))
        print(f'  PrimaryMoveType selected text="{primary_text}" expected="{("Full In" if intype == "Load In" else intype)}"', flush=True)
    except Exception:
        pass
    debug_locator_state(page, 'SecondaryMoveType', '#SecondaryMoveType')
    try:
        secondary_value = clean_ssco_value(page.locator("#SecondaryMoveType").first.input_value(timeout=500))
        expected_secondary = "ExportsEmptyOut" if outtype == "Empty Out" else "ImportsFullOut" if outtype == "Load Out" else outtype
        print(f'  SecondaryMoveType selected value="{secondary_value}" expected="{expected_secondary}"', flush=True)
    except Exception:
        pass
    debug_locator_state(page, 'IN booking input', "xpath=//*[@id='BookingNumber']")
    debug_locator_state(page, 'IN empty container input', "xpath=//*[@id='EmptyInAppts_0__ApptInfo_ContainerNumber']")
    debug_locator_state(page, 'OUT booking input', "xpath=//div[@id='divUpdatePanel-OUT']//input[@id='BookingNumber']")
    debug_locator_state(page, 'OUT container input', "xpath=//div[@id='divUpdatePanel-OUT']//input[@id='ContainerNumber']")
    debug_locator_state(page, 'OUT pin/BOL input', "xpath=//div[@id='divUpdatePanel-OUT']//input[contains(@id,'PinNumber')]")
    debug_locator_state(page, 'OUT submit button', "xpath=//div[@id='divUpdatePanel-OUT']//button[.//span[normalize-space()='Submit'] or normalize-space()='Submit']")
    debug_locator_state(page, 'OUT go button', "xpath=//div[@id='divUpdatePanel-OUT']//button[.//span[normalize-space()='Go'] or normalize-space()='Go']")

def debug_visible_messages(browser):
    page = browser._page
    print('DEBUG visible portal messages after waiting for result:', flush=True)
    for selector in [
        "xpath=//*[contains(@class,'error') and normalize-space()]",
        "xpath=//div[contains(@class,'ui-dialog-content')]//*[normalize-space()]",
        "xpath=//*[contains(@class,'validation') and normalize-space()]",
    ]:
        try:
            locator = page.locator(selector)
            for ix in range(min(locator.count(), 10)):
                item = locator.nth(ix)
                if item.is_visible(timeout=250):
                    text = clean_ssco_value(item.inner_text(timeout=250))
                    if text:
                        print(f'  message: {text[:250]}', flush=True)
        except Exception:
            pass

def wait_for_coupled_load_out_ready(browser, panel_xpath, timeout=30):
    page = browser._page
    pin_selector = f"xpath={panel_xpath}//input[contains(@id,'PinNumber') and not(@disabled)]"
    submit_selector = (
        f"xpath={panel_xpath}//button["
        f"(.//span[normalize-space()='Submit'] or normalize-space()='Submit') and not(@disabled)]"
    )
    print('Waiting for coupled Load Out fields after container GO', flush=True)

    def ready(driver):
        try:
            pin_ready = page.locator(pin_selector).first.is_visible(timeout=500)
            submit_ready = page.locator(submit_selector).first.is_visible(timeout=500)
            return pin_ready and submit_ready
        except Exception:
            return False

    try:
        WebDriverWait(browser, timeout, poll_frequency=0.25).until(ready)
        print('Coupled Load Out PIN/BOL and Submit controls are ready', flush=True)
    except TimeoutException:
        debug_paired_move_state(browser, 'coupled load out readiness timeout', None, 'Load Out')
        raise

def click_coupled_load_out_submit(page, panel_xpath, timeout=20000):
    selector = (
        f"xpath={panel_xpath}//input[contains(@id,'PinNumber')]/ancestor::div[contains(@id,'ContainerAppts')][1]"
        "//button[(.//span[normalize-space()='Submit'] or normalize-space()='Submit') and not(@disabled)]"
    )
    locator = page.locator(selector).first
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.scroll_into_view_if_needed(timeout=5000)
        ctrl_id = locator.get_attribute("id")
        ctrl_text = clean_ssco_value(locator.inner_text(timeout=500))
        print(f'Clicking coupled Load Out Submit control id={ctrl_id} text="{ctrl_text}"', flush=True)
        locator.click()
        return True
    except Exception as exc:
        print(f'Coupled Load Out specific submit not found; falling back to panel submit: {exc}', flush=True)
        return click_panel_submit(page, panel_xpath, timeout=timeout)

def click_panel_submit(page, panel_xpath, timeout=20000):
    submit_locators = [
        page.locator(f"xpath={panel_xpath}//button[.//span[normalize-space()='Submit'] and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//button[normalize-space()='Submit' and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//input[(@type='submit' or @type='button') and normalize-space(@value)='Submit' and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//*[self::button or self::a or self::input][contains(normalize-space(.),'Submit') and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//button[.//span[normalize-space()='Submit'] and not(@disabled)]").last,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//button[normalize-space()='Submit' and not(@disabled)]").last,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//input[(@type='submit' or @type='button') and normalize-space(@value)='Submit' and not(@disabled)]").last,
    ]

    last_error = None
    for locator in submit_locators:
        try:
            locator.wait_for(state="visible", timeout=timeout // len(submit_locators))
            locator.scroll_into_view_if_needed(timeout=5000)
            ctrl_id = locator.get_attribute("id")
            ctrl_text = clean_ssco_value(locator.inner_text(timeout=500))
            print(f'Clicking Submit control id={ctrl_id} text="{ctrl_text}"', flush=True)
            locator.click()
            return True
        except Exception as exc:
            last_error = exc

    controls = page.locator(
        f"xpath={panel_xpath}/ancestor::form[1]//*[self::button or self::a or self::input]"
    )
    try:
        print('Visible controls near OUT panel:', flush=True)
        for ix in range(min(controls.count(), 25)):
            ctrl = controls.nth(ix)
            if ctrl.is_visible(timeout=250):
                text = ctrl.inner_text(timeout=250) if ctrl.evaluate("el => el.tagName !== 'INPUT'") else ctrl.get_attribute("value")
                ctrl_id = ctrl.get_attribute("id")
                ctrl_type = ctrl.get_attribute("type")
                print(f'  control id={ctrl_id} type={ctrl_type} text={text}', flush=True)
    except Exception:
        pass

    raise last_error if last_error else TimeoutException("Could not find Submit button")

def click_panel_go(page, panel_xpath, timeout=20000):
    go_locators = [
        page.locator(f"xpath={panel_xpath}//button[normalize-space()='Go' and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//button[.//span[normalize-space()='Go'] and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//input[(@type='submit' or @type='button') and translate(normalize-space(@value), 'GO', 'go')='go' and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}//*[self::button or self::a or self::input][translate(normalize-space(.), 'GO', 'go')='go' and not(@disabled)]").first,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//button[normalize-space()='Go' and not(@disabled)]").last,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//button[.//span[normalize-space()='Go'] and not(@disabled)]").last,
        page.locator(f"xpath={panel_xpath}/ancestor::form[1]//input[(@type='submit' or @type='button') and translate(normalize-space(@value), 'GO', 'go')='go' and not(@disabled)]").last,
    ]

    last_error = None
    for locator in go_locators:
        try:
            locator.wait_for(state="visible", timeout=timeout // len(go_locators))
            locator.scroll_into_view_if_needed(timeout=5000)
            locator.click()
            return True
        except Exception as exc:
            last_error = exc

    raise last_error if last_error else TimeoutException("Could not find Go button")

def ensure_checkbox(browser, xpath, checked=True, timeout=10):
    checkbox = WebDriverWait(browser, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    if checkbox.is_checked() != checked:
        browser.execute_script("arguments[0].click();", checkbox)
    return checkbox

def wait_for_async(browser, timeout=20):
    WebDriverWait(browser, timeout).until(
        lambda d: d.execute_script("""
            return !window.Sys ||
                   !Sys.WebForms ||
                   !Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack();
        """)
    )

def select_secondary_move(browser, outtype, timeout=20):
    select_elem = WebDriverWait(browser, timeout).until(
        EC.presence_of_element_located((By.ID, "SecondaryMoveType"))
    )

    WebDriverWait(browser, timeout).until(
        lambda d: d.execute_script(
            "return !document.getElementById('SecondaryMoveType').disabled;"
        )
    )

    if outtype == 'Empty Out':
        Select(select_elem).select_by_value('ExportsEmptyOut')
    elif outtype == 'Load Out':
        Select(select_elem).select_by_value('ImportsFullOut')

    return select_elem

def wait_for_paired_move_ready(browser, intype, outtype, timeout=20):
    page = browser._page
    expected_primary = "Full In" if intype == "Load In" else intype
    expected_secondary = "ExportsEmptyOut" if outtype == "Empty Out" else "ImportsFullOut"

    inbound_ready_xpath = "//*[@id='BookingNumber']"
    if intype == "Empty In":
        inbound_ready_xpath = "//*[@id='EmptyInAppts_0__ApptInfo_ContainerNumber']"

    outbound_field_xpath = "//div[@id='divUpdatePanel-OUT']//input[@id='BookingNumber']"
    if outtype == "Load Out":
        outbound_field_xpath = "//div[@id='divUpdatePanel-OUT']//input[@id='ContainerNumber']"

    print('Waiting for paired move page state to settle', flush=True)
    wait_for_async(browser)
    time.sleep(1.0)

    def paired_state_is_ready(driver):
        try:
            in_checked = page.locator("#IsInMove").is_checked(timeout=500)
            out_checked = page.locator("#IsOutMove").is_checked(timeout=500)
            primary_text = clean_ssco_value(
                page.locator("#PrimaryMoveType option:checked").first.text_content(timeout=500)
            )
            secondary_value = clean_ssco_value(
                page.locator("#SecondaryMoveType").first.input_value(timeout=500)
            )
            inbound_visible = page.locator(f"xpath={inbound_ready_xpath}").first.is_visible(timeout=500)
            out_panel_attached = page.locator("xpath=//div[@id='divUpdatePanel-OUT']").first.count() > 0
            outbound_attached = page.locator(f"xpath={outbound_field_xpath}").first.count() > 0
            return (
                in_checked
                and out_checked
                and primary_text == expected_primary
                and secondary_value == expected_secondary
                and inbound_visible
                and out_panel_attached
                and outbound_attached
            )
        except Exception:
            return False

    try:
        WebDriverWait(browser, timeout, poll_frequency=0.25).until(paired_state_is_ready)
    except TimeoutException:
        debug_paired_move_state(browser, 'paired move readiness timeout', intype, outtype)
        raise
    print('Paired move page state is ready', flush=True)

def open_new_preadvise(browser, url, timeout=20):
    target_xpath = '//div[@id="divUpdatePanel-IN"]'

    print(f'Opening New Pre-Advise page: {url}', flush=True)
    browser.get(url)

    try:
        return browser.attached_xpath(target_xpath, timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        print('Hash route did not open New Pre-Advise; trying menu clicks', flush=True)

    print('Opening New Pre-Advise from menu', flush=True)
    try_new_preadvise_menu(browser)
    return browser.attached_xpath(target_xpath, timeout=timeout * 1000)

def logonfox(err):
    username = usernames['gate']
    password = passwords['gate']
    print('username,password=', username, password)
    print('Entering Playwright Chromium') if printif == 1 else 1
    logontrys = 1
    logonyes = 0
    url1 = websites['gate']
    newurl = ''

    browser = launch_browser()
    browser.maximize_window()
    browser.get(url1)
    wait = WebDriverWait(browser, 30)

    print(f'Logon try {logontrys}')

    try:
        try:
            browser._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        wait.until(
            lambda d: d.find_elements(By.ID, "UserName") and d.find_elements(By.ID, "Password")
        )

        # Username
        user_elem = fill_input_and_verify(browser, By.ID, "UserName", username, "Username")

        # Password
        pass_elem = fill_input_and_verify(browser, By.ID, "Password", password, "Password")
        print('Submitting login form', flush=True)
        browser.execute_script("arguments[0].scrollIntoView({block:'center'});", pass_elem)
        pass_elem.locator.click()
        pass_elem.submit()
        browser.press_enter()
        try:
            browser._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        try:
            browser._page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(1)

    except TimeoutException:
        err.append('Login fields did not appear within timeout')
        return browser, newurl, logonyes, logontrys, err

    # Wait for successful login. This app can leave the URL looking like the
    # login route while the authenticated SPA shell is already visible.
    try:
        wait.until(
            lambda d: (
                'logon' not in d.current_url.lower()
                or d.find_elements(By.XPATH, "//div[@id='divUpdatePanel-IN']")
                or d.page_has_text("Pre-Advise")
                or d.page_has_text("New Pre-Advise")
                or d.page_has_text("Appointment")
            )
        )
        print(f'Login completion detected at URL: {browser.current_url}', flush=True)
        logonyes = 1
        newurl = browser.current_url
    except TimeoutException:
        print(f'Login wait timed out at URL: {browser.current_url}', flush=True)
        err.append('Login failed after submit')
        return browser, newurl, logonyes, logontrys, err

    if logonyes:
        newurl = appointment_url_from(newurl)
        try:
            open_new_preadvise(browser, newurl)
        except PlaywrightTimeoutError:
            err.append('Logged in but New Pre-Advise page did not open')

    return browser, newurl, logonyes, logontrys, err


def pinscraper(p,d,inbox,outbox,intype,outtype,browser,url,jx):
    pinget = 0
    error = 0
    thisdate = datetime.strftime(p.Date + timedelta(0), '%m/%d/%Y')
    print(f'The pins will be created for date: {thisdate} for url {url}')

    if 1 == 1:
        open_new_preadvise(browser, url)

        softwait(browser, '//*[@id="IsInMove"]')
        print('url=', url, flush=True)
        textboxx = "//*[contains(text(),'Pre-Advise created successfully')]"
        closebutx = "//*[contains(@type,'button')]"
        print(f'inbox is {inbox}')
        paired_moves_initialized = False

        if inbox:

            print(f'URL at beginning of inbox section is {url}')
            #set_checkbox(browser, '//*[@id="IsInMove"]', checked=True) #Wait for and check the inbox
            ensure_checkbox(browser, '//*[@id="IsInMove"]', checked=True)

            if intype == 'Load In':

                if not paired_moves_initialized:
                    hard_select_option(browser, "PrimaryMoveType", "Full In")

                softwait(browser, '//*[@id="BookingNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="BookingNumber"]')
                selectElem.send_keys(p.InBook)
                selectElem.submit()

                # We could have an issue with the booking for the load in so need to error check here
                text, error = wait_for_booking_result(browser)
                print(f'The load in text is {text} and error is {error}')
                if error:
                    print('Writing the error for booking inbound box to the database')
                    pinget = 0
                    p.Notes = f'Error: {text[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Intext}'
                    p.Intext = modtext
                    db.session.commit()
                    return

                #softwait(browser, '//*[@id="FullInAppts_0__ContainerNumber"]')
                #Dont have to softwait anymore becauce the wait_for_booking error check does this now

                #Load In Driver info
                note_text = fillapptdata(browser, d, p, thisdate)

                #Load In Completion of container and chassis
                selectElem = browser.find_element_by_xpath('//*[@id="FullInAppts_0__ContainerNumber"]')
                selectElem.send_keys(p.InCon)
                selectElem = browser.find_element_by_xpath('//*[@id="FullInAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                selectElem.send_keys(chas)
                selectElem.submit()

                #Load In wait for textbox and extract
                #print(f'Performing softwait_long for textboxx: {textboxx}')
                #softwait_long(browser, textboxx)
                #pintext = get_text(browser, textboxx)
                pintext, error = get_result_message(browser)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    try:
                        pinin = pins[0]
                        print(f'The load in pin is {pinin}')
                        pinget = 1
                        p.InPin = str(pinin)
                        p.OutPin = '1'
                        intext = p.Intext
                        if hasinput(intext):
                            p.Intext = f'[*{pinin}*] {intext}'
                        else:
                            p.Intext = f'[*{pinin}*] Load In: *{p.InBook}  {p.InCon}*'
                        db.session.commit()
                    except:
                        print(f'Could not locate the PIN text for Load In {p.InCon}')
                else:
                    p.Intext = f'Error: {p.Intext}'
                    p.Notes = f'Error: {pintext}'
                    p.Active = 0
                    db.session.commit()
                    return

                closethepopup(browser, closebutx)

            else:

                #Empty In Start with Container number
                if not paired_moves_initialized:
                    hard_select_option(browser, "PrimaryMoveType", "Empty In")


                softwait(browser, '//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ContainerNumber"]')
                selectElem.send_keys(p.InCon)
                commit_field_without_enter(selectElem.locator)
                wait_for_ssco_populated(
                    browser,
                    ssco_xpath='//*[@id="EmptyInAppts_0__ApptInfo_SscoCode"]'
                )

                # In this case there is no error check on the container until the submit button is hit

                # Empty In Driver Data
                note_text = fillapptdata(browser, d, p, thisdate)

                #Empty In Completion for Chassis
                selectElem = browser.find_element_by_xpath('//*[@id="EmptyInAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                chas = p.InChas
                if not hasinput(chas): chas = f'{scac}007'
                selectElem.send_keys(chas)
                selectElem.submit()

                #Empty In wait for textbox and extract
                #softwait_long(browser, textboxx)
                pintext, error = get_result_message(browser)
                #pintext = get_text(browser, textboxx)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinin = pins[0]
                    print(f'The empty in pin is {pinin}')
                    pinget = 1
                    p.InPin = str(pinin)
                    p.OutPin = '1'
                    intext = p.Intext
                    if hasinput(intext):
                        p.Intext = f'[*{pinin}*] {intext}'
                    else:
                        p.Intext = f'[*{pinin}*] Empty In: *{p.InCon}*'
                    db.session.commit()

                else:
                    p.Intext = f'Error: {p.Intext}'
                    p.Notes = f'Error: {pintext}'
                    p.Active = 0
                    db.session.commit()
                    return

                closethepopup(browser, closebutx)

        if outbox:

            print(f'URL at beginning of outbox section is {url}')
            ensure_checkbox(browser, '//*[@id="IsOutMove"]', checked=True)

            wait_for_async(browser)

            selectElem = WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.ID, "SecondaryMoveType"))
            )

            WebDriverWait(browser, 20).until(
                lambda d: d.execute_script(
                    "return !document.getElementById('SecondaryMoveType').disabled;"
                )
            )

            if outtype == 'Empty Out':
                if not paired_moves_initialized:
                    Select(selectElem).select_by_value('ExportsEmptyOut')

                # We need to know if inbox because there is different about of things to do depending...
                if not inbox:
                    # If there is no inbox it is much easier to find the booking number section as there is only
                    # one of them, but also there are more elements to be filled out

                    #Select(selectElem).select_by_value('ExportsEmptyOut')
                    booking = WebDriverWait(browser, 20).until(
                        EC.element_to_be_clickable((By.ID, "BookingNumber"))
                    )
                    booking.clear()
                    booking.send_keys(p.OutBook)
                    booking.submit()
                    # With no inbox there is the possibility of a bad booking we need to check for the
                    # error right here


                    text, error = wait_for_booking_result(browser)
                    print(f'The empty out text is {text} and error is {error}')
                    if error:
                        print('Writing the error for booking with no inbound box to the database')
                        pinget = 0
                        p.Notes = f'Error: {text[:190]}'
                        p.Active = 0
                        modtext = f'Error on: {p.Outtext}'
                        p.Outtext = modtext
                        db.session.commit()
                        return

                    #If there is no incoming box then we have to fill the driver data also
                    softwait(browser, '//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    note_text = fillapptdata(browser, d, p, thisdate)
                    selectElem = browser.find_element_by_xpath('//*[@id="EmptyOutAppts_0__ExpressGateModel_MainMove_ChassisNumber"]')
                    selectElem.send_keys(p.OutChas)
                    selectElem.submit()
                else:
                    # If there is an inbox, then there is the possibility of two elements with ID=bookingnumber,
                    # and that greatly complicates selenium search to find correct element, we need to restrain
                    # it to the outbox section

                    #The information is different with inbox already setting the chassis and appt information, just have to find and hit the submit button
                    print('Using coupled Empty Out path with inbound move; only OutBook should be entered', flush=True)
                    panel_xpath = "//div[@id='divUpdatePanel-OUT']"
                    page = browser._page
                    booking_locator = page.locator(
                        f"xpath={panel_xpath}//input[@id='BookingNumber' and not(@disabled)]"
                    ).first
                    booking_locator.wait_for(state="visible", timeout=20000)
                    booking_locator.fill("")
                    booking_locator.type(str(p.OutBook), delay=25)
                    commit_field_without_enter(booking_locator)
                    click_panel_go(page, panel_xpath)
                    time.sleep(0.5)
                    click_panel_submit(page, panel_xpath)


                print(f'Locating element with text: {textboxx}')
                #softwait_long(browser, textboxx)
                pintext, error = get_result_message(browser)

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinout = pins[0]
                    print(f'The empty out pin is {pinout}')
                    pinget = 1
                    p.OutPin = str(pinout)
                    outtext = p.Outtext
                    if hasinput(outtext):
                        p.Outtext = f'[*{pinout}*] {outtext}'
                    else:
                        p.Outtext = f'[*{pinout}*] Empty Out: *{p.OutBook}*'
                    db.session.commit()
                else:
                    #There is an error within the popup we need to display
                    print('Writing the error for empty out with a good booking but no pintext found')
                    pinget = 0
                    p.Notes = f'Error: {pintext[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Outtext}'
                    p.Outtext = modtext
                    db.session.commit()

                closethepopup(browser, closebutx)

            if outtype == 'Load Out':
                if not paired_moves_initialized:
                    Select(selectElem).select_by_value('ImportsFullOut')
                # if empty in there will be two container number xpaths, have to use full xpath....
                # Scope the container number input to the OUT panel
                panel_xpath = "//div[@id='divUpdatePanel-OUT']"
                container_xpath = f"{panel_xpath}//input[@id='ContainerNumber']"

                containerid = WebDriverWait(browser, 20).until(
                    EC.element_to_be_clickable((By.XPATH, container_xpath))
                )

                containerid.clear()
                containerid.send_keys(p.OutCon)
                containerid.submit()

                #Check here for error on container pull, instant errors like unavailable
                text, error = wait_for_container_result(browser)
                print(f'The load out text is {text} and error is {error}')
                if error:
                    pinget = 0
                    p.Notes = f'Error: {text[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Outtext}'
                    p.Outtext = modtext
                    db.session.commit()
                    return


                softwait(browser, '//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]')

                # Only fill in the driver/truck data if no in box, otherwise it is there already
                if not inbox: note_text = fillapptdata(browser, d, p, thisdate)

                selectElem = browser.find_element_by_xpath('//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_PinNumber"]')
                selectElem.send_keys(p.OutBook)

                # Only input the chassis number for the outbox if there is no inbox
                if not inbox:
                    selectElem = browser.find_element_by_xpath('//*[@id="ContainerAppts_0__ApptInfo_ExpressGateModel_MainMove_ChassisNumber"]')
                    chas = p.OutChas
                    if not hasinput(chas): chas = f'{scac}007'
                    selectElem.send_keys(chas)

                selectElem.submit()

                # The popup box is different if there is an incoming box....
                #softwait_long(browser, textboxx)
                #pintext = get_text(browser, textboxx)
                pintext, error = get_result_message(browser)

                print(f'The pintext found here is: {pintext} in element {selectElem}')

                if not error:
                    pins = [int(s) for s in pintext.split() if s.isdigit()]
                    pinout = pins[0]
                    print(f'The load out pin is {pinout}')
                    pinget = 1
                    p.OutPin = str(pinout)
                    outtext = p.Outtext
                    if hasinput(outtext):
                        p.Outtext = f'[*{pinout}*] {outtext}'
                    else:
                        p.Outtext = f'[*{pinout}*] Load Out: *{p.OutBook}  {p.OutCon}*'
                    db.session.commit()

                else:
                    #There is an error within the popup we need to display
                    pinget = 0
                    p.Notes = f'Error: {pintext[:190]}'
                    p.Active = 0
                    modtext = f'Error on: {p.Outtext}'
                    p.Outtext = modtext
                    db.session.commit()

                closethepopup(browser, closebutx)


    if pinget:
        if inbox and not outbox: p.Outtext = 'Nothing Out'
        if outbox and not inbox: p.Intext = f'Bare chassis in {p.InChas}'
        p.Phone = d.Phone
        p.Notes = note_text
        db.session.commit()





#*********************************************************************
conyes = 0
contrys = 0
print(f'Attempting to connect to database and table Pins....')
while contrys < 4 and conyes == 0:
    try:
        pdata = Pins.query.filter((Pins.OutPin == '0') &
                (Pins.Active == 1) & (Pins.Date >= today) & (Pins.Maker == 'WEB')).all()
        nruns = len(pdata)
        conyes = 1
    except:
        print(f'Could not connect to database on try {contrys}')
        contrys += 1
    time.sleep(1)

if nruns == 0 or conyes == 0:
    if conyes == 0:
        print('Could not connect to database')
    else:
        print(f'There are no pins required per database')
    quit()

if nruns > 0:
    print(f'The pin database requires {nruns} new interchange sequences as follows:')
    for pdat in pdata:
        if hasinput(pdat.InBook): intype = 'Load In'
        elif hasinput(pdat.InCon): intype = 'Empty In'
        else:
            intype = 'NoInType'
            inbox = 0

        if hasinput(pdat.OutCon): outtype = 'Load Out'
        elif hasinput(pdat.OutBook): outtype = 'Empty Out'
        else:
            outtype = 'NoOutType'
            outbox = 0
        print(f'Date: {pdat.Date} Driver: {pdat.Driver} Unit: {pdat.Unit} In-Type: {intype}  Out-Type: {outtype}')



if nruns > 0:
    logonyes = 0
    logontrys = 0
    #Log on to browser
    err = []
    browser, url, logonyes, logontrys, err = logonfox(err)


if logonyes:
    for jx, pdat in enumerate(pdata):
        inbox = 1
        outbox = 1

        if hasinput(pdat.InBook): intype = 'Load In'
        elif hasinput(pdat.InCon): intype = 'Empty In'
        else:
            intype = 'NoInType'
            inbox = 0

        if hasinput(pdat.OutCon): outtype = 'Load Out'
        elif hasinput(pdat.OutBook): outtype = 'Empty Out'
        else:
            outtype = 'NoOutType'
            outbox = 0

        if outbox and inbox:
            if not hasinput(pdat.OutChas):
                pdat.OutChas = pdat.InChas
                db.session.commit()

        ddat = Drivers.query.filter(Drivers.Name==pdat.Driver).first()
        if ddat is not None:
            print(f'We have driver {ddat.Name} with phone {ddat.Phone}')
            print(f'We have driver {ddat.Name} driving truck {pdat.Unit} with tag {pdat.Tag}')
            print(f'On date {pdat.Date} we have intype {intype} in-booking {pdat.InBook} and in-container {pdat.InCon} and in-chassis {pdat.InChas}')
            print(f'On date {pdat.Date} we have outtype {outtype} Out-booking {pdat.OutBook} and Out-container {pdat.OutCon} and Out-chassis {pdat.OutChas}')
            pinscraper(pdat,ddat,inbox,outbox,intype,outtype,browser,url,jx)
            print(f'The url after return from pinscraper is {url}')
        else:
            print(f'There is incomplete data for driver {pdat.Driver}')

    browser.quit()
if nt == 'remote': tunnel.stop()
