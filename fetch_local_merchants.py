import requests
import re
from bs4 import BeautifulSoup
from job_dashboard import build_dashboard

def get_local_merchants_ddg(search_term="wholesale distributor Kenya"):
    # Target DuckDuckGo's lightweight, non-JS endpoint
    url = "https://duckduckgo.com"
    
    print(f"Initializing search aggregation pipeline for: '{search_term}'...")
    
    payload = {'q': search_term}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Request raw HTML from the anonymous search node
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Target the standard web result blocks
            search_results = soup.find_all('div', class_='result')
            print(f"Successfully processed search query! Found {len(search_results)} primary operational targets.")
            
            local_listings = []
            
            for result in search_results:
                title_element = result.find('a', class_='result__url')
                snippet_element = result.find('a', class_='result__snippet')
                
                if title_element and snippet_element:
                    raw_name = title_element.text.strip()
                    raw_url = title_element['href']
                    description = snippet_element.text.strip()
                    
                    # Clean up the business name (remove trailing URLs if DDG appends them)
                    clean_name = re.sub(r'\s+http.*$', '', raw_name)
                    # Limit length for clean dashboard cards
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
                    
            return local_listings
        else:
            print(f"Network node rejected pipeline. Status code: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"An error occurred during target ingestion: {e}")
        return []

if __name__ == "__main__":
    # Fetch live businesses from the search pipeline
    merchant_leads = get_local_merchants_ddg()
    
    if merchant_leads:
        print("Processing targets through your custom scoring engine...")
        build_dashboard(merchant_leads)
    else:
        print("No business entries retrieved. Try modifying your search parameters.")
