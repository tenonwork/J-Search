import asyncio
from playwright.async_api import async_playwright
import json

async def scrape_local_merchants():
    # Pivoting target to wholesale suppliers and commercial merchant groups
    url = "https://yellowpageskenya.com"
    
    print("Launching headless browser via Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Connecting to mid-tier merchant directories...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Grabbing elements using flexible text-focused structures
            business_cards = await page.locator("div.listing-details, .business-card").all()
            print(f"Found {len(business_cards)} mid-sized merchant profiles.")
            
            local_leads = []
            
            for card in business_cards[:15]:
                try:
                    name_el = card.locator("h2, .business-name")
                    phone_el = card.locator(".tele, .phone-number, .mobile")
                    
                    name = await name_el.text_content() if await name_el.count() > 0 else "Unknown Merchant"
                    phone = await phone_el.text_content() if await phone_el.count() > 0 else "No Phone Listed"
                    
                    company_data = {
                        "company_name": name.strip(),
                        "phone": phone.strip(),
                        "segment": "Wholesale / Retail Tech"
                    }
                    
                    local_leads.append(company_data)
                    print(f"Target Acquired: {company_data['company_name']}")
                except Exception as card_err:
                    continue
                
            with open("local_merchant_leads.json", "w", encoding="utf-8") as f:
                json.dump(local_leads, f, indent=4)
                
            print("\nSuccessfully compiled mid-tier targets to 'local_merchant_leads.json'!")
            
        except Exception as e:
            print(f"Connection failed or page timed out: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_local_merchants())
