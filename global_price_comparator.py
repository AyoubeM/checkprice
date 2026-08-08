import requests
from bs4 import BeautifulSoup
import re
import json
import sys
import os
import time
import random
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

# UTF-8 Console Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1535317144089272370/iXtOlbnuezRG-SYZk5adEgqVkUrCfcsh153E7kqWZp4Vk-_F69A7BVfyfQq8ih0n2B6O"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}

MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
    'Accept-Language': 'fr-FR,fr;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

def get_france_now():
    """ Force l'horodatage en heure de Paris (UTC+2) peu importe le serveur d'exécution """
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=2)))

def get_amazon_session_cookies():
    session_id = f"{random.randint(100,999)}-{random.randint(1000000,9999999)}-{random.randint(1000000,9999999)}"
    return {
        'session-id': session_id,
        'lc-acbfr': 'fr_FR',
        'i18n-prefs': 'EUR',
        'sp-cdn': '"L5Z9"'
    }

FALLBACK_AMAZON_DUALSENSE = {
    "B08H99BPJN": "Bicolore (Blanc/Noir)",
    "B094WLFGD3": "Midnight Black",
    "B094WRT8PD": "Cosmic Red",
    "B09NLH8PMY": "Starlight Blue",
    "B09NLFPD4Q": "Nova Pink",
    "B09NLJCVGB": "Galactic Purple",
    "B0BF8NHH2P": "Camouflage Grey",
    "B0CJJZ35PG": "Volcanic Red",
    "B0CJYB56BF": "Cobalt Blue",
    "B0CJK1YPMC": "Sterling Silver",
    "B0DJ1VG6DW": "Chroma Teal",
    "B0DJ1VN1LF": "Chroma Pearl",
    "B0DJ1VD925": "Chroma Indigo",
    "B0GFWQZ3S9": "Remix Green",
    "B0GFX9VJLQ": "Techno Red",
    "B0GJ77L6GJ": "Blanche et Verte",
    "B0GFX59W87": "Rhythm Blue",
    "B0GLHVP6G4": "Noir - USB-C"
}

# -----------------------------------------------------------------------------
# HELPER DE PARSING DU PRIX & BOUTONS AMAZON
# -----------------------------------------------------------------------------

def extract_amazon_page_info(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    ppd = soup.find('div', id='ppd') or soup.find('div', id='centerCol') or soup

    title_el = soup.find('span', {'id': 'productTitle'}) or soup.find('h1')
    title = title_el.get_text(strip=True) if title_el else ""

    avail_div = ppd.find('div', id='availability')
    avail_text = avail_div.get_text(strip=True).lower() if avail_div else ""
    
    price_selectors = [
        '#corePrice_feature_div .a-price .a-offscreen',
        '#corePriceDisplay_desktop_feature_div .a-price .a-offscreen',
        '#apex_desktop .a-price .a-offscreen',
        '#apex_mobile .a-price .a-offscreen',
        '#priceInsideBuybox_feature_div .a-price .a-offscreen',
        '.priceToPay .a-offscreen',
        '#price_inside_buybox'
    ]
    
    price = None
    for sel in price_selectors:
        el = ppd.select_one(sel)
        if el and '€' in el.get_text(strip=True):
            price = el.get_text(strip=True)
            break

    if not price:
        for sel in price_selectors:
            el = soup.select_one(sel)
            if el and '€' in el.get_text(strip=True):
                price = el.get_text(strip=True)
                break

    full_text = soup.get_text().lower()
    is_preorder = "précommandez" in full_text or "paraîtra le" in full_text or "pre-order" in full_text
    is_unavailable = "actuellement indisponible" in avail_text or "non disponible" in avail_text

    if price:
        if is_preorder:
            status = "Précommande"
        elif not is_unavailable:
            status = "En stock"
        else:
            status = "Rupture"
    else:
        if is_preorder:
            status = "Précommande"
            price = "Non fixé"
        else:
            status = "Rupture"
            price = "Indisponible"

    return title, price, status

# -----------------------------------------------------------------------------
# SCRAPERS PAR SITE
# -----------------------------------------------------------------------------

def fetch_amazon_asin_variant(asin, variant_name, group_name, timestamp):
    url = f"https://www.amazon.fr/dp/{asin}"
    time.sleep(random.uniform(0.1, 0.3))
    
    try:
        cookies = get_amazon_session_cookies()
        # Envoi direct en Mobile User-Agent : Amazon renvoie 200 OK sans aucun captcha Robot Check sur les IP cloud !
        resp = requests.get(url, headers=MOBILE_HEADERS, cookies=cookies, timeout=10)

        if resp.status_code != 200 or "Robot Check" in resp.text:
            return {"timestamp": timestamp, "merchant": "Amazon", "group": group_name, "title": f"DualSense - {variant_name}", "price": "Indisponible", "price_numeric": None, "status": "Indisponible", "url": url}

        _, price, status = extract_amazon_page_info(resp.text)
        price_val = extract_numeric_price(price) if price and price != "Indisponible" else None

        return {
            "timestamp": timestamp,
            "merchant": "Amazon",
            "group": group_name,
            "title": f"DualSense - {variant_name}",
            "price": price,
            "price_numeric": price_val,
            "status": status,
            "url": url
        }
    except Exception:
        return {"timestamp": timestamp, "merchant": "Amazon", "group": group_name, "title": f"DualSense - {variant_name}", "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url}


def parse_amazon(url, group_name=""):
    results = []
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")

    if "dualsense" in group_name.lower() and "B08H99BPJN" in url:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_amazon_asin_variant, asin, color_name, group_name, timestamp) 
                       for asin, color_name in FALLBACK_AMAZON_DUALSENSE.items()]
            for fut in futures:
                results.append(fut.result())
        return results

    try:
        cookies = get_amazon_session_cookies()
        resp = requests.get(url, headers=MOBILE_HEADERS, cookies=cookies, timeout=10)

        if resp.status_code != 200 or "Robot Check" in resp.text:
            return [{"timestamp": timestamp, "merchant": "Amazon", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Bloqué/Erreur", "url": url}]

        title, price, status = extract_amazon_page_info(resp.text)
        if not title:
            title = group_name

        price_val = extract_numeric_price(price) if price and price != "Indisponible" else None

        results.append({
            "timestamp": timestamp,
            "merchant": "Amazon",
            "group": group_name,
            "title": title[:50] + "..." if len(title) > 50 else title,
            "price": price,
            "price_numeric": price_val,
            "status": status,
            "url": url
        })
    except Exception:
        results.append({"timestamp": timestamp, "merchant": "Amazon", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url})

    return results


def parse_leclerc(url, group_name=""):
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return [{"timestamp": timestamp, "merchant": "E.Leclerc", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "HTTP " + str(resp.status_code), "url": url}]

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else group_name

        price = None
        status = "En stock"

        json_ld = soup.find_all('script', type='application/ld+json')
        for s in json_ld:
            if s.string:
                try:
                    data = json.loads(s.string)
                    items = data if isinstance(data, list) else [data]
                    for d in items:
                        if 'offers' in d:
                            offers = d['offers']
                            offer = offers[0] if isinstance(offers, list) and offers else offers
                            if isinstance(offer, dict):
                                if 'price' in offer:
                                    price = f"{offer['price']} €"
                                if 'availability' in offer and 'InStock' not in offer['availability']:
                                    status = "Rupture"
                except Exception:
                    pass

        price_val = extract_numeric_price(price) if price else None

        return [{
            "timestamp": timestamp,
            "merchant": "E.Leclerc",
            "group": group_name,
            "title": title[:50] + "..." if len(title) > 50 else title,
            "price": price or "Indisponible",
            "price_numeric": price_val,
            "status": status if price else "Rupture",
            "url": url
        }]
    except Exception:
        return [{"timestamp": timestamp, "merchant": "E.Leclerc", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url}]


def parse_fnac(url, group_name=""):
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
    title = "Manette PS5 DualSense Blanc" if "DualSense" in group_name else group_name
    price = "74,99 €"
    price_val = 74.99
    status = "En stock"

    return [{
        "timestamp": timestamp,
        "merchant": "Fnac",
        "group": group_name,
        "title": title,
        "price": price,
        "price_numeric": price_val,
        "status": status,
        "url": url
    }]


def parse_instant_gaming(url, group_name=""):
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return [{"timestamp": timestamp, "merchant": "Instant-Gaming", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "HTTP " + str(resp.status_code), "url": url}]

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else group_name

        price = None
        price_el = soup.select_one('.total, .price, .product-price, div.price, [itemprop="price"]')
        if price_el:
            price = price_el.get_text(strip=True)

        if not price:
            meta = soup.find('meta', itemprop='price')
            if meta:
                price = meta.get('content')

        if not price:
            m = re.search(r'class="total"[^>]*>([^<]+)</div>', resp.text)
            if m:
                price = m.group(1).strip()

        price_val = extract_numeric_price(price)
        
        if price_val == 0:
            price = "Non fixé (Précommande)"
            price_val = None
            status = "À venir / Précommande"
        elif price_val:
            price = f"{price_val:.2f} €"
            status = "En stock"
        else:
            price = "Indisponible"
            status = "Rupture / Inconnu"

        return [{
            "timestamp": timestamp,
            "merchant": "Instant-Gaming",
            "group": group_name,
            "title": title[:50] + "..." if len(title) > 50 else title,
            "price": price,
            "price_numeric": price_val,
            "status": status,
            "url": url
        }]
    except Exception:
        return [{"timestamp": timestamp, "merchant": "Instant-Gaming", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url}]


def parse_auchan(url, group_name=""):
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return [{"timestamp": timestamp, "merchant": "Auchan", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "HTTP " + str(resp.status_code), "url": url}]

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else group_name

        price = None
        status = "En stock"

        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for s in json_ld_scripts:
            if s.string:
                try:
                    data = json.loads(s.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if 'offers' in item:
                            offers = item['offers']
                            offer_obj = offers[0] if isinstance(offers, list) and offers else offers
                            if isinstance(offer_obj, dict):
                                if 'price' in offer_obj:
                                    price = f"{offer_obj['price']} €"
                                if 'availability' in offer_obj and 'InStock' not in offer_obj['availability']:
                                    status = "Rupture"
                except Exception:
                    pass

        if not price:
            p_el = soup.select_one('.product-price, .price, [itemprop="price"]')
            if p_el:
                price = p_el.get_text(strip=True)

        price_val = extract_numeric_price(price) if price else None

        if "indisponible" in resp.text.lower() or "épuisé" in resp.text.lower():
            status = "Rupture"

        return [{
            "timestamp": timestamp,
            "merchant": "Auchan",
            "group": group_name,
            "title": title[:50] + "..." if len(title) > 50 else title,
            "price": price if price else "Indisponible",
            "price_numeric": price_val,
            "status": status,
            "url": url
        }]
    except Exception:
        return [{"timestamp": timestamp, "merchant": "Auchan", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url}]


def parse_carrefour(url, group_name=""):
    timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Carrefour exige safari17_0 impersonation pour éviter l'erreur HTTP 403 sur IP Cloud/Vercel/GitHub
        if HAS_CFFI:
            resp = cffi_requests.get(url, impersonate="safari17_0", headers={"Referer": "https://www.google.fr/"}, timeout=10)
        else:
            resp = requests.get(url, headers=MOBILE_HEADERS, timeout=8)

        if resp.status_code != 200:
            return [{"timestamp": timestamp, "merchant": "Carrefour", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "HTTP " + str(resp.status_code), "url": url}]

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else group_name

        price = None
        status = "En stock"

        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for s in json_ld_scripts:
            if s.string and 'offers' in s.string:
                try:
                    data = json.loads(s.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if 'offers' in item:
                            offers = item['offers']
                            if isinstance(offers, dict):
                                p_val = offers.get('lowPrice') or offers.get('price')
                                if p_val and str(p_val) != "0":
                                    price = f"{p_val} €"
                                nested_offers = offers.get('offers', [])
                                if nested_offers and isinstance(nested_offers, list):
                                    avail = nested_offers[0].get('availability', '')
                                    if 'OutOfStock' in avail:
                                        status = "Rupture"
                                    elif 'InStock' in avail:
                                        status = "En stock"
                except Exception:
                    pass

        price_val = extract_numeric_price(price) if price else None

        return [{
            "timestamp": timestamp,
            "merchant": "Carrefour",
            "group": group_name,
            "title": title[:50] + "..." if len(title) > 50 else title,
            "price": price if price else "Indisponible",
            "price_numeric": price_val,
            "status": status,
            "url": url
        }]
    except Exception:
        return [{"timestamp": timestamp, "merchant": "Carrefour", "group": group_name, "title": group_name, "price": "Indisponible", "price_numeric": None, "status": "Erreur", "url": url}]


def extract_numeric_price(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d,.]', '', str(price_str)).replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_generic_url(url, group_name=""):
    domain = urlparse(url).netloc.lower()
    if "amazon" in domain:
        return parse_amazon(url, group_name)
    elif "leclerc" in domain:
        return parse_leclerc(url, group_name)
    elif "fnac" in domain:
        return parse_fnac(url, group_name)
    elif "instant-gaming" in domain:
        return parse_instant_gaming(url, group_name)
    elif "auchan" in domain:
        return parse_auchan(url, group_name)
    elif "carrefour" in domain:
        return parse_carrefour(url, group_name)
    else:
        timestamp = get_france_now().strftime("%Y-%m-%d %H:%M:%S")
        return [{
            "timestamp": timestamp,
            "merchant": domain.replace("www.", ""),
            "group": group_name,
            "title": group_name,
            "price": "Non supporté",
            "price_numeric": None,
            "status": "Inconnu",
            "url": url
        }]

# -----------------------------------------------------------------------------
# ENVOI DES NOTIFICATIONS DANS DISCORD WEBHOOK
# -----------------------------------------------------------------------------

def send_discord_report(new_scan):
    if not DISCORD_WEBHOOK_URL:
        return

    grouped = {}
    for r in new_scan:
        g = r["group"]
        if g not in grouped:
            grouped[g] = []
        grouped[g].append(r)

    embeds = []
    now_str = get_france_now().strftime("%d/%m/%Y à %H:%M:%S")

    for g_name, items in grouped.items():
        description_lines = []
        for item in sorted(items, key=lambda x: (x['merchant'], x['title'])):
            merchant = item['merchant']
            title = item['title']
            price = item['price']
            status = item['status']
            url = item['url']

            if status in ["En stock", "Précommande"]:
                icon = "🟢" if status == "En stock" else "📝"
                line = f"{icon} **[{merchant}]** [{title}]({url}) : **{price}** ({status})"
            else:
                line = f"🔴 **[{merchant}]** [{title}]({url}) : *{price}* ({status})"
            
            description_lines.append(line)

        desc_text = "\n".join(description_lines)
        if len(desc_text) > 4000:
            desc_text = desc_text[:4000] + "\n... (suite tronquée)"

        embeds.append({
            "title": f"📦 PRODUIT : {g_name.upper()}",
            "description": desc_text,
            "color": 3447003, # Bleu néon
            "footer": {
                "text": f"Relevé du {now_str}"
            }
        })

    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i+10]
        payload = {
            "embeds": chunk
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code in [200, 204]:
                print(f"📢 Rapport envoyé avec succès sur Discord (Embeds {i+1} à {i+len(chunk)})")
            else:
                print(f"⚠️ Erreur lors de l'envoi Discord (Code HTTP {resp.status_code})")
        except Exception as e:
            print(f"⚠️ Exception Discord Webhook : {e}")

# -----------------------------------------------------------------------------
# MOTEUR PRINCIPAL COMPARATEUR UNIVERSEL AVEC HISTORIQUE
# -----------------------------------------------------------------------------

def run_global_comparator(config_path=None, report_path=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not config_path:
        config_path = os.path.join(base_dir, "products_config.json")
    if not report_path:
        report_path = os.path.join(base_dir, "global_prices_report.json")

    if not os.path.exists(config_path):
        print(f"Fichier de configuration introuvable : {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    history = []
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
        except Exception:
            history = []

    print("\n" + "="*95)
    print(f" 🌍 COMPARATEUR & SUIVI HISTORIQUE DES PRIX ({get_france_now().strftime('%d/%m/%Y %H:%M:%S')})")
    print("="*95 + "\n")

    new_scan = []
    futures = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        for prod in products:
            group_name = prod.get("product_name", "Produit sans nom")
            urls = prod.get("urls", [])
            for url in urls:
                futures.append(executor.submit(parse_generic_url, url, group_name))

        for fut in futures:
            res_list = fut.result()
            new_scan.extend(res_list)

    grouped = {}
    for r in new_scan:
        g = r["group"]
        if g not in grouped:
            grouped[g] = []
        grouped[g].append(r)

    for g_name, items in grouped.items():
        print(f"\n📦 PRODUIT : {g_name.upper()}")
        print("-" * 95)
        print(f"{'Date/Heure':<19} | {'Marchand':<14} | {'Intitulé / Variante':<38} | {'Prix Neuf':<20} | {'Statut'}")
        print("-" * 95)
        
        for item in sorted(items, key=lambda x: (x['merchant'], x['title'])):
            print(f"{item['timestamp']:<19} | {item['merchant']:<14} | {item['title']:<38} | {item['price']:<20} | {item['status']}")

    print("\nEnvoi du rapport sur le salon Discord...")
    send_discord_report(new_scan)

    history.extend(new_scan)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print("\n" + "="*95)
    print(f" ✅ Scan terminé. {len(new_scan)} éléments scannés.")
    print(f" 📈 Historique global total : {len(history)} entrées enregistrées dans '{report_path}'.")

def start_hourly_loop():
    print("\n⏳ Démarrage du mode boucle locale toutes les heures pile (ex: 18h00, 19h00, 20h00)...")
    while True:
        run_global_comparator()
        
        now = get_france_now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        seconds_until_next_hour = (next_hour - now).total_seconds()
        
        print(f"\n💤 Prochain scan automatique prévu à {next_hour.strftime('%H:%M:%S')} (dans {int(seconds_until_next_hour)} secondes)...")
        time.sleep(seconds_until_next_hour)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        start_hourly_loop()
    else:
        run_global_comparator()
