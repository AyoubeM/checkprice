from http.server import BaseHTTPRequestHandler
import json
import sys
import os

# Ajouter le répertoire racine au PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from global_price_comparator import run_global_comparator

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Exécuter le comparateur et envoyer le rapport sur le salon Discord
            run_global_comparator()
            
            response_data = {
                "status": "success",
                "message": "Scan effectué et rapport transmis sur Discord Webhook avec succès !"
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
        
        except Exception as e:
            error_data = {
                "status": "error",
                "message": str(e)
            }
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(error_data, ensure_ascii=False).encode('utf-8'))
