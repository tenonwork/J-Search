import requests
import json
from job_dashboard import build_dashboard

def get_local_merchants(region="Kenya"):
    url = "https://overpass-api.de/api/interpreter"
    
    print(f"Connecting to OpenStreetMap Overpass API for {region}...")
    
    query = """[out:json][timeout:30];
    area["ISO3166-1"="KE"]->.searchArea;
    (
      nwr["shop"~"wholesale|distributor|warehouse"](area.searchArea);
      nwr["commercial"~"wholesale|logistics"](area.searchArea);
    );
    out tags;"""
    
    # 1. Supply descriptive headers to bypass the 406 content block rules
    headers = {
        "User-Agent": "TenonworkOperationalAuditPipeline/1.0 (contact: swainaina551@gmail.com)",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
    }
    
    # 2. Package the query parameter payload explicitly
    payload = {"data": query}
    
    try:
        # Utilizing standard POST requests with safe timeout controls
        response = requests.post(url, data=payload, headers=headers, timeout=40)
        
        if response.status_code == 200:
            raw_data = response.json()
            elements = raw_data.get('elements', [])
            
            print(f"Successfully retrieved {len(elements)} live local business profiles!")
            local_listings = []
            
            for item in elements:
                tags = item.get('tags', {})
                name = tags.get('name', 'Unbranded Local Merchant')
                
                # Check for standard location details
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
        else:
            print(f"OSM Server rejected connection. Status code: {response.status_code}")
            # If the main server is busy, we print the response text to debug
            print(f"Server message snippet: {response.text[:200]}")
            return []
            
    except Exception as e:
        print(f"An error occurred while connecting to spatial directory: {e}")
        return []

if __name__ == "__main__":
    merchant_leads = get_local_merchants()
    
    if merchant_leads:
        print("Processing local business profiles through your custom scoring engine...")
        build_dashboard(merchant_leads)
    else:
        print("No merchant profiles found to display. Try running again.")
