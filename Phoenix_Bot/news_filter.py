import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz

# --- CONFIGURATION ---
XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
TARGET_CURRENCIES = ["USD"]  # Gold is driven entirely by USD news
EMBARGO_MINUTES = 30         # Block trades 30 mins before and after

_cached_events = []
_last_fetch_time = None

def fetch_this_weeks_news():
    """Downloads the raw XML data from Forex Factory securely."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(XML_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"⚠️ Failed to fetch news calendar: {e}", flush=True)
        return None

def parse_news(xml_data):
    """Filters for High Impact USD news and converts to local time."""
    events = []
    if not xml_data: return events
    
    # Forex factory XML outputs in US/Eastern.
    eastern_tz = pytz.timezone('US/Eastern')
    # We want to convert it to whatever timezone the local machine (server) is running on.
    local_tz = datetime.now().astimezone().tzinfo
    
    try:
        root = ET.fromstring(xml_data)
        for event in root.findall('event'):
            impact = event.find('impact').text.strip() if event.find('impact') is not None else ""
            country = event.find('country').text.strip() if event.find('country') is not None else ""
            
            if impact == "High" and country in TARGET_CURRENCIES:
                date_str = event.find('date').text.strip()
                time_str = event.find('time').text.strip()
                title = event.find('title').text.strip()
                
                # Skip 'All Day' events like Bank Holidays
                if not time_str or time_str.lower() in ["all day", "tentative"]:
                    continue
                    
                dt_str = f"{date_str} {time_str}"
                try:
                    # Parse the string into a naive datetime object
                    dt_naive = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    # Force the naive datetime to be understood as US/Eastern
                    dt_eastern = eastern_tz.localize(dt_naive, is_dst=None)
                    # Convert to the local machine's timezone
                    dt_local = dt_eastern.astimezone(local_tz).replace(tzinfo=None)
                    
                    events.append({
                        "title": title,
                        "time": dt_local
                    })
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Error parsing XML: {e}", flush=True)
        
    return events

def is_news_embargo():
    """
    Called by main.py. Returns True and the event name if inside the danger zone.
    """
    global _cached_events, _last_fetch_time
    now = datetime.now()
    
    # Refresh the calendar automatically once every 12 hours
    if _last_fetch_time is None or (now - _last_fetch_time).total_seconds() > 43200:
        xml_data = fetch_this_weeks_news()
        if xml_data:
            _cached_events = parse_news(xml_data)
            _last_fetch_time = now
            print(f"📰 News Calendar Synced: Tracking {len(_cached_events)} High-Impact USD events.", flush=True)
        
    for event in _cached_events:
        time_diff = (now - event['time']).total_seconds()
        
        # If the current time is within +/- 30 minutes of the news event
        if abs(time_diff) <= (EMBARGO_MINUTES * 60):
            return True, event['title']
            
    return False, ""