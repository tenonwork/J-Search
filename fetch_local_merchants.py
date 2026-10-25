import requests
import json
import time
from job_dashboard import build_dashboard

def get_local_merchants(region="Kenya"):
    # A list of completely different, independent public mirror servers
    overpass_servers = [
        "https://kumi.systems",       # Highly reliable private mirror
        "https://overpass-api.de",             # Main German server (with overflow)
        "https://openstreetmap.ru"    # Alternative European mirror
    ]
    
    print(f"Initializing spatial pipeline for {region}...")
    
    query = """[out:json][timeout:25];
    area["ISO3166-1"="KE"]->.searchArea;
    (
      nwr["shop"~"wholesale|distributor|warehouse"](area.searchArea);
      nwr["commercial"~"wholesale|logistics"](area.searchArea);
    );
    out tags;"""
    
    headers = {
        "User-Agent": "TenonworkOperationalAuditPipeline/1.0 (contact: swainaina551@gmail.com)",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
    }
    payload = {"data": query}
    
    raw_data = None
    
    # Loop through each server until one works
    for idx, url in enumerate(overpass_servers):
        print(f"Attempting connection to Server {idx+1}/{len(overpass_servers)}: {url.split('/')[2]}...")
        try:
            # Shorter timeout per server so we failover quickly if one is hanging
            response = requests.post(url, data=payload, headers=headers, timeout=20)
            
            if response.status_code == 200:
                raw_data = response.json()
                print("Server connection established successfully!")
                break # We got our data, break out of the server fallback loop
            else:
                print(f"-> Server {idx+1} busy. Status code: {response.status_code}. Moving to next mirror...")
                
        except (requests.exceptions.RequestException, Exception) as e:
            print(f"-> Server {idx+1} timed out or failed. Moving to next mirror...")
            continue
            
    if not raw_data:
        print("\nAll public Overpass servers are currently at capacity due to global traffic limits.")
        print("Recommendation: Wait 1-2 minutes and execute python fetch_local_merchants.py again.")
        return []
        
    elements = raw_data.get('elements', [])
    print(f"Successfully retrieved {len(elements)} live local business profiles!")
    local_listings = []
    
    for item in elements:
        tags = item.get('tags', {})
        name = tags.get('name', 'Unbranded Local Merchant')
        
        city = tags.get('addr:city', tags.get('is_in:city', ''))
        suburb = tags.get('addr:suburb', tags.get('addr:neighborhood', ''))
        location_str = f"{suburb}, {city}".strip(", ") if (suburb or city) else "East Africa Regional Center"
        
        description = f"Operational merchant node. Type-tagging: {', '.join(tags.keys())}. "
        if 'operator' in tags: description += f"Managed by {tags['operator']}. "
        
        formatted_business = {
            "title": "Local B2B Architecture Audit Opportunity",
            "company": name,
            "location": f"Local ({location_str})",
            "url": tags.get('website', f"https://google.com{name.replace(' ', '+')}+Kenya"),
            "desc": description
        }
        local_listings.append(formatted_business)
        
    return local_listings

if __name__ == "__main__":
    merchant_leads = get_local_merchants()
    
    if merchant_leads:
        print("Processing local business profiles through your custom scoring engine...")
        build_dashboard(merchant_leads)
