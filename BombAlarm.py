import requests
import json
import csv
import pathlib
import re
import os
import time
import math
import datetime
from urllib.parse import quote

def fetch_biwapp_news():
    url = "https://www.biwapp.de/widget/dataBiwappProxy"
    form_data = {
        "location": "allPWA"
    }
    
    try:
        response = requests.post(url, data=form_data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON response")
    
    return None

def clean_html(text):
    """
    Clean HTML tags from text for Discord formatting
    """
    if not isinstance(text, str):
        return str(text)
    
    # Replace <br> tags with newlines
    text = re.sub(r'<br\s*/?>', '\n', text)
    
    # Replace <b> tags with Discord bold formatting
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text)
    
    # Handle other HTML tags if needed
    text = re.sub(r'<[^>]+>', '', text)  # Remove any other HTML tags
    
    # Remove excessive newlines (more than 2 in a row)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text

def is_bomb_related(title, details):
    """
    Check if the alert is related to bombs by checking for keywords in title or details
    """
    # Convert to lowercase strings for case-insensitive matching
    if not isinstance(title, str):
        title = str(title).lower()
    else:
        title = title.lower()
        
    if not isinstance(details, str):
        details = str(details).lower()
    else:
        details = details.lower()
    
    # First check if this is an "Entwarnung" (all-clear) - if so, ignore it
    if "entwarnung" in title or "entwarnung" in details:
        print(f"  - Ignoring alert: contains 'Entwarnung' (all-clear)")
        return False
    
    # List of bomb-related keywords in German
    bomb_keywords = [
        "bombe", "bomben", "bombenfund", "bombenentschärfung", "bombenverdacht",
        "fliegerbombe", "fliegerbomben", "weltkriegsbombe", "sprengkörper",
        "kampfmittel", "explosiv", "entschärfung", "evakuierung", "evakuierungsmaßnahmen"
    ]
    
    # Check if any keyword is in title or details
    for keyword in bomb_keywords:
        if keyword in title or keyword in details:
            print(f"  + Alert contains bomb-related keyword: {keyword}")
            return True
    
    print(f"  - Alert doesn't match any bomb-related keywords")
    return False

def parse_polygon(polygon_str):
    """
    Parse polygon string format like "POLYGON ((8.512233 53.210926, 8.525872 53.201079, ...))"
    into a GeoJSON format for Mapbox
    """
    if not isinstance(polygon_str, str):
        return None
    
    try:
        # Extract coordinates from the POLYGON string
        match = re.search(r'POLYGON\s*\(\((.*?)\)\)', polygon_str)
        if not match:
            return None
        
        # Get the coordinate pairs
        coords_str = match.group(1)
        coord_pairs = coords_str.split(',')
        coordinates = []
        
        # Process each coordinate pair
        for pair in coord_pairs:
            lon, lat = pair.strip().split()
            coordinates.append([float(lon), float(lat)])
        
        # Calculate center point for map centering
        center_x = sum(coord[0] for coord in coordinates) / len(coordinates)
        center_y = sum(coord[1] for coord in coordinates) / len(coordinates)
        
        return {
            "coordinates": coordinates,
            "center": [center_x, center_y]
        }
    except Exception as e:
        print(f"Error parsing polygon: {e}")
        return None

def calculate_zoom_level(coordinates):
    """
    Calculate appropriate zoom level based on the size of the polygon
    """
    if not coordinates or len(coordinates) < 3:  # Need at least 3 points for a polygon
        return 13  # Default zoom level
    
    # Calculate bounding box
    lons = [coord[0] for coord in coordinates]
    lats = [coord[1] for coord in coordinates]
    
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    
    # Calculate width and height in degrees
    width_deg = max_lon - min_lon
    height_deg = max_lat - min_lat
    
    # Use the larger dimension to determine zoom level
    # These values are approximations and may need adjustment
    # Mapbox zoom: 0 = world, 20 = building level
    if width_deg > 0.5 or height_deg > 0.5:
        zoom = 9  # Very large area
    elif width_deg > 0.2 or height_deg > 0.2:
        zoom = 11  # Large area
    elif width_deg > 0.1 or height_deg > 0.1:
        zoom = 12  # Medium area
    else:
        zoom = 13  # Tiny area
    
    # Calculate a more precise zoom level based on the map dimensions
    # Formula: zoom = log2(360 / degrees) for longitude
    lon_zoom = math.log2(360 / max(width_deg * 1.5, 0.0001))  # Avoid division by zero
    lat_zoom = math.log2(170 / max(height_deg * 1.5, 0.0001))  # 170 degrees is approximate north-south range
    
    # Use the smaller zoom (which shows more area)
    calculated_zoom = min(lon_zoom, lat_zoom)
    
    # Combine both approaches and apply reasonable limits
    zoom = min(max(round(calculated_zoom), 8), 16)  # Limit between 8 and 16
    
    print(f"Calculated zoom level: {zoom} for polygon width={width_deg:.5f}°, height={height_deg:.5f}°")
    return zoom

def generate_map_image(polygon_data, alert_id):
    """
    Generate a static map image from Mapbox using polygon data
    """
    # Mapbox access token - you'll need to replace this with your own token
    MAPBOX_TOKEN = "pk.eyJ1Ijoic2FpY29kZSIsImEiOiJjbHdveWNpa2wwNzRpMmpxZDZvb2Rhc2JiIn0.xrWc6YAbB0eSHvCDpOu9ZQ"
    
    if not polygon_data or not polygon_data["coordinates"]:
        return None
    
    try:
        # Create GeoJSON for the polygon
        geojson = {
            "type": "Feature",
            "properties": {
                "stroke": "#FF4444",
                "stroke-width": 3,
                "stroke-opacity": 1,
                "fill": "#FF4444",
                "fill-opacity": 0.4
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_data["coordinates"]]
            }
        }
        
        # Center coordinates and zoom level
        center_x, center_y = polygon_data["center"]
        zoom = calculate_zoom_level(polygon_data["coordinates"])
        
        # Create the URL for the static map with polygon - using dark theme
        encoded_geojson = quote(json.dumps(geojson))
        url = f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/geojson({encoded_geojson})/{center_x},{center_y},{zoom}/1280x720?access_token={MAPBOX_TOKEN}&logo=false&attribution=false"
        
        # Download the image
        response = requests.get(url)
        response.raise_for_status()
        
        # Save the image
        image_path = pathlib.Path(__file__).parent / f"alert_map_{alert_id}.png"
        with open(image_path, "wb") as f:
            f.write(response.content)
        
        print(f"Map image saved to {image_path}")
        return image_path
        
    except Exception as e:
        print(f"Error generating map image: {e}")
        return None

def load_sent_alert_ids():
    """
    Load previously sent alert IDs from a file
    """
    sent_ids_file = pathlib.Path(__file__).parent / "sent_alerts.json"
    
    if not os.path.exists(sent_ids_file):
        # Create empty file if it doesn't exist
        with open(sent_ids_file, 'w') as f:
            json.dump([], f)
        return []
    
    try:
        with open(sent_ids_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading sent alert IDs: {e}")
        return []

def save_sent_alert_id(alert_id):
    """
    Add a new alert ID to the sent alerts file
    """
    sent_ids_file = pathlib.Path(__file__).parent / "sent_alerts.json"
    sent_ids = load_sent_alert_ids()
    
    # Add the new ID if it's not already in the list
    if alert_id not in sent_ids:
        sent_ids.append(alert_id)
        
        # Save the updated list
        try:
            with open(sent_ids_file, 'w') as f:
                json.dump(sent_ids, f)
            print(f"Added alert ID {alert_id} to sent alerts tracking")
        except Exception as e:
            print(f"Error saving sent alert ID: {e}")

def parse_date_to_timestamp(date_str):
    """
    Parse a date string into a Discord timestamp format
    """
    if date_str == 'N/A':
        return 'N/A'
    
    try:
        # Try different date formats
        formats = [
            '%d.%m.%Y %H:%M:%S',  # 09.03.2023 11:43:53
            '%d.%m.%Y %H:%M',     # 09.03.2023 11:43
            '%Y-%m-%d %H:%M:%S',   # 2023-03-09 11:43:53
            '%Y-%m-%dT%H:%M:%S',   # 2023-03-09T11:43:53
            '%Y-%m-%dT%H:%M:%SZ',  # 2023-03-09T11:43:53Z
        ]
        
        dt = None
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        
        if dt is None:
            print(f"Could not parse date: {date_str}")
            return date_str
        
        # Convert to Unix timestamp (seconds since epoch)
        timestamp = int(dt.timestamp())
        
        # Format for Discord <t:timestamp:f> (full date and time)
        return f"<t:{timestamp}:f>"
    
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        return date_str

def post_to_discord(alert_data):
    """
    Post the newest alert to Discord webhook with map image as an embed
    """
    webhook_url = "https://discord.com/api/webhooks/1348335731290144948/LxJMGG9_YAvvSjEf4DjLLTXZbn6dLsHy4C-fddYs3R4yT1qD7yKKbqOjMkKvY0xCmaf2"
    
    if not alert_data:
        print("No alert data to post to Discord")
        return
    
    # Clean HTML from text fields
    title = clean_html(alert_data['Title'])
    details = clean_html(alert_data['Details'])
    
    # Create thread name for the forum
    thread_title = f"Bombenalarm - {title[:30]}..." if len(title) > 30 else f"Bombenalarm - {title}"
    
    # Format dates as Discord timestamps
    valid_from = parse_date_to_timestamp(alert_data['Valid From'])
    valid_until = parse_date_to_timestamp(alert_data['Valid Until'])
    
    # Generate map image if area polygon is available
    map_image_path = None
    wme_link = None
    
    if alert_data['Area'] != 'N/A':
        polygon_data = parse_polygon(alert_data['Area'])
        if polygon_data:
            # Calculate zoom level for both map image and WME link
            zoom_level = calculate_zoom_level(polygon_data["coordinates"])
            map_image_path = generate_map_image(polygon_data, alert_data['ID'])
            
            # Create WME link using center coordinates and calculated zoom level
            if "center" in polygon_data and len(polygon_data["center"]) == 2:
                center_lon, center_lat = polygon_data["center"]  # Note: polygon_data returns [lon, lat]
                wme_link = f"https://www.waze.com/de/editor?env=row&lat={center_lat}&lon={center_lon}&zoomLevel={zoom_level}"
    
    try:
        # Create an embed for better formatting (translated to German)
        embed = {
            "title": title,
            "description": details,
            "color": 15158332,
            "fields": [
                {
                    "name": "Gültig von",
                    "value": valid_from,
                    "inline": True
                },
                {
                    "name": "Gültig bis",
                    "value": valid_until,
                    "inline": True
                },
                {
                    "name": "Absender",
                    "value": alert_data['Sender'],
                    "inline": False
                }
            ],
            "footer": {
                "text": f"Alarm-ID: {alert_data['ID']}"
            },
        }
        
        # Add WME link if coordinates are available
        if wme_link:
            embed["fields"].append({
                "name": "Waze Map Editor",
                "value": wme_link,
                "inline": False
            })
        
        # Base payload with thread_name and embed
        payload = {
            "thread_name": thread_title,
            "embeds": [embed]
        }
        
        # If we have an image, use multipart/form-data
        if map_image_path and os.path.exists(map_image_path):
            # Add a placeholder in the embed for the attached image
            embed["image"] = {"url": "attachment://map.png"}
            
            # Create the payload as a string
            payload_json = json.dumps(payload)
            
            # Set up the multipart form data
            form_data = {
                "payload_json": payload_json
            }
            
            with open(map_image_path, "rb") as img:
                files = {"file": ("map.png", img)}
                response = requests.post(webhook_url, data=form_data, files=files)
        else:
            # No image, use regular JSON payload
            response = requests.post(webhook_url, json=payload)
            
        response.raise_for_status()
        print(f"Erfolgreich gesendet: Alarm {alert_data['ID']} zum Discord-Forum")
        
        # Record that this alert was successfully sent
        save_sent_alert_id(str(alert_data['ID']))
        
        return True
    except requests.RequestException as e:
        print(f"Fehler beim Senden an Discord-Webhook: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Antwort: {e.response.text}")
        return False
    finally:
        # Clean up the image file
        if map_image_path and os.path.exists(map_image_path):
            try:
                os.remove(map_image_path)
                print(f"Entfernte temporäres Kartenbild: {map_image_path}")
            except Exception as e:
                print(f"Fehler beim Entfernen des temporären Kartenbilds: {e}")

def save_news_to_csv(news_data):
    if not news_data:
        print("No news data available.")
        return 0
    
    # Load previously sent alert IDs
    sent_alert_ids = load_sent_alert_ids()
    print(f"Loaded {len(sent_alert_ids)} previously sent alert IDs")
    
    # Determine data structure and extract news items
    news_items = []
    if isinstance(news_data, list):
        news_items = news_data
    elif isinstance(news_data, dict):
        # Try common patterns in API responses
        for key in ["items", "data", "news", "messages"]:
            if key in news_data and isinstance(news_data[key], list):
                news_items = news_data[key]
                break
    
    if not news_items:
        print("Could not find news items in the response data.")
        return 0
    
    print(f"Found {len(news_items)} total news items")
    
    # Filter news items for category 16 only
    category_16_items = []
    for item in news_items:
        if not isinstance(item, dict):
            continue
        
        # Check for category field with value 16
        for field in ["category", "type", "categoryId", "category_id"]:
            if field in item and (item[field] == 16 or item[field] == "16"):
                category_16_items.append(item)
                break
    
    print(f"Found {len(category_16_items)} category 16 news items")
    
    if not category_16_items:
        print("No category 16 news items found.")
        return 0
    
    # Format data for CSV and filter for bomb-related alerts
    csv_data = []
    new_alerts = []
    
    print("Filtering for bomb-related alerts...")
    for item in category_16_items:
        row = {}
        
        # Extract ID
        item_id = "N/A"
        for field in ["id", "newsId", "message_id"]:
            if field in item:
                item_id = item[field]
                row["ID"] = item_id
                break
        else:
            row["ID"] = item_id
        
        # Skip if this alert has already been sent
        if str(item_id) in sent_alert_ids:
            print(f"Skipping already sent alert ID: {item_id}")
            continue
        
        # Extract title
        title = "N/A"
        for field in ["title", "headline", "subject"]:
            if field in item:
                title = item[field]
                row["Title"] = title
                break
        else:
            row["Title"] = title
        
        # Extract details
        details = "N/A"
        for field in ["details", "message", "content", "text", "description"]:
            if field in item:
                details = item[field]
                row["Details"] = details
                break
        else:
            row["Details"] = details
        
        print(f"\nChecking alert ID {item_id}: '{title[:50]}...'")
        
        # Check if this alert is bomb-related - if not, skip it
        if not is_bomb_related(title, details):
            print(f"  - Skipping: not bomb-related")
            continue
            
        print(f"  + Including bomb-related alert: {item_id}")
            
        # Extract the rest of the fields
        # Extract valid_from
        for field in ["valid_from", "validFrom", "startDate", "start_date"]:
            if field in item:
                row["Valid From"] = item[field]
                break
        else:
            row["Valid From"] = "N/A"
        
        # Extract valid_until
        for field in ["valid_until", "validUntil", "endDate", "end_date"]:
            if field in item:
                row["Valid Until"] = item[field]
                break
        else:
            row["Valid Until"] = "N/A"
        
        # Extract area
        for field in ["area", "polygon", "geolocation"]:
            if field in item:
                row["Area"] = item[field]
                break
        else:
            row["Area"] = "N/A"
        
        # Extract sender
        for field in ["sender", "author", "source"]:
            if field in item:
                row["Sender"] = item[field]
                break
        else:
            row["Sender"] = "N/A"
        
        csv_data.append(row)
        new_alerts.append(row)  # Track new alerts for sending
    
    print(f"\nFound {len(new_alerts)} new bomb-related alerts")
    
    # Write to CSV file
    csv_file_path = pathlib.Path(__file__).parent / "alerts.csv"
    try:
        if csv_data:
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = csv_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_data)
                print(f"Successfully saved {len(csv_data)} bomb-related alerts to {csv_file_path}")
                
                # Post all new alerts to Discord
                if new_alerts:
                    print(f"Found {len(new_alerts)} new bomb-related alerts to send")
                    for alert in new_alerts:
                        print(f"Posting bomb alert {alert['ID']} to Discord...")
                        post_to_discord(alert)
                        # Add a small delay between posts to avoid rate limiting
                        time.sleep(2)
                else:
                    print("No new bomb-related alerts to send.")
        else:
            print("No bomb-related alerts found to write to CSV.")
    except Exception as e:
        print(f"Error writing CSV file: {e}")
        
    return len(new_alerts)  # Return count of new alerts processed

def main():
    print("Starte BIWAPP Bombenalarm-Überwachung...")
    
    try:
        while True:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"\n[{current_time}] Suche nach neuen Alarmen...")
            
            # Fetch and process news
            news_data = fetch_biwapp_news()
            if news_data:
                new_alerts_count = save_news_to_csv(news_data)
                if new_alerts_count > 0:
                    print(f"Verarbeitet: {new_alerts_count} neue Alarme")
                else:
                    print("Keine neuen Alarme gefunden")
            else:
                print("Fehler beim Abrufen der Nachrichtendaten")
            
            # Wait for 2 minutes before checking again
            print(f"Warte 2 Minuten bis zur nächsten Prüfung...")
            time.sleep(120)  # 120 seconds = 2 minutes
            
    except KeyboardInterrupt:
        print("\nÜberwachung durch Benutzer gestoppt")
    except Exception as e:
        print(f"Fehler in der Hauptschleife: {e}")
        raise

if __name__ == "__main__":
    main()
