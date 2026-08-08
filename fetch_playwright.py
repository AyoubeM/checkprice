import sys
import time

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    url = sys.argv[1]
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36',
                extra_http_headers={'Accept-Language': 'fr-FR,fr;q=0.9'}
            )
            page.goto(url, wait_until='domcontentloaded', timeout=25000)
            time.sleep(1.5)
            content = page.content()
            browser.close()
            # Write HTML output to stdout encoded in utf-8
            sys.stdout.buffer.write(content.encode('utf-8'))
    except Exception as e:
        sys.exit(1)

if __name__ == '__main__':
    main()
