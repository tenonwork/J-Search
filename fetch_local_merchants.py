import requests
import json
from job_dashboard import build_dashboard

def get_local_merchants(region="Kenya"):
    # Overpass API endpoint for OpenStreetMap data
    url = "https://overpass-api.de"
    
    print(f"Connecting to OpenStreetMap Overpass API for {region}...")
    
    # This query hunts for commercial shops, wholesalers, and retail distributors
    # [timeout:25] ensures the network query drops cleanly if the server lags
    query = f"""
    [out:json][timeout:25];
    area["ISO3166-1"="KE"]->.searchArea;
    (
      nwr["shop"="wholesale"](area.searchArea);
      nwr["shop"="distributor"](area.searchArea);
      nwr["commercial"="wholesale"](area.searchArea);
    );
    out tags;
    """
    
    try:
        response = requests.post(url, data={"data": query}, timeout=30)
        
        if response.status_code == 200:
            raw_data = response.json()
            elements = raw_data.get('elements', [])
            
            print(f"Successfully retrieved {len(elements)} live local business profiles!")
            local_listings = []
            
            for item in elements:
                tags = item.get('tags', {})
                name = tags.get('name', 'Unbranded Local Merchant')
                
                # Extract location tags cleanly
                city = tags.get('addr:city', '')
                suburb = tags.get('addr:suburb', '')
                location_str = f"{suburb}, {city}".strip(", ") if (suburb or city) else "East Africa Regional Hub"
                
                # Construct a clean text description for your scoring engine to analyze
                description = f"Local retail and wholesale merchant operation. Tags: {', '.join(tags.keys())}. "
                if 'operator' in tags: description += f"Operated by {tags['operator']}. "
                if 'description' in tags: description += f"{tags['description']}"
                
                formatted_business = {
                    "title": f"B2B Operational Audit / Tech Infrastructure Needs",
                    "company": name,
                    "location": f"Local ({location_str})",
                    "url": tags.get('website', f"https://google.com{name.replace(' ', '+')}+Kenya"),
                    "desc": description
                }
                local_listings.append(formatted_business)
                
            return local_listings
        else:
            print(f"OSM Server rejected connection. Status code: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"An error occurred while connecting to spatial directory: {e}")
        return []

if __name__ == "__main__":
    # Fetch real merchant locations across Kenya
    merchant_leads = get_local_merchants()
    
    if merchant_leads:
        print("Processing local business profiles through your custom scoring engine...")
        # Direct integration back into your unified UI system!
        build_dashboard(merchant_leads)
    else:
        print("No merchant profiles found to display.")
