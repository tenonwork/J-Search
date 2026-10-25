import requests
import re
from bs4 import BeautifulSoup
from job_dashboard import build_dashboard

def get_local_merchants_ddg(search_term="wholesale distributor Kenya"):
    url = "https://html.duckduckgo.com/html/"
    
    print(f"Initializing search aggregation pipeline for: '{search_term}'...")
    
    payload = {'q': search_term}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Target the standard web result blocks
            search_results = soup.find_all('div', class_='result')
            local_listings = []
            
            for result in search_results:
                # FIX: Target 'result__a' instead of 'result__url'
                title_element = result.find('a', class_='result__a')
                snippet_element = result.find('a', class_='result__snippet')
                
                if title_element and snippet_element:
                    raw_name = title_element.text.strip()
                    raw_url = title_element['href']
                    description = snippet_element.text.strip()
                    
                    clean_name = re.sub(r'\s+http.*$', '', raw_name)
                    if len(clean_name) > 50:
                        clean_name = clean_name[:47] + "..."
                    
                    formatted_business = {
                        "title": "Local B2B Tooling Audit Opportunity",
                        "company": clean_name,
                        "location": "Local (East Africa Hub)",
                        "url": raw_url,
                        "desc": f"{description} | Context-Tags: wholesale, retail supplier, merchant infrastructure."
                    }
                    local_listings.append(formatted_business)
            
            print(f"Successfully processed search query! Found {len(local_listings)} operational targets.")
            return local_listings
        else:
            print(f"Network node rejected pipeline. Status code: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"An error occurred during target ingestion: {e}")
        return []

if __name__ == "__main__":
    merchant_leads = get_local_merchants_ddg()
    
    if merchant_leads:
        print("Processing targets through your custom scoring engine...")
        build_dashboard(merchant_leads)
    else:
        print("No business entries retrieved. Try modifying your search parameters.")
