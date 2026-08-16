import httpx
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone

# 1. Poné tus credenciales reales de Railway acá
API_URL = "https://dunner-production.up.railway.app" 
WEBHOOK_SECRET="8cc67c08964d884bb97a156e267c6489a2f09c9a6e446a7383464c6058369b0a"
API_KEY="9dfa1c5cbb914f1444edb2dcda5250592727ca827ee9c29cfcb766e98e95651e"

# 2. Simulamos el webhook de un pago rechazado por falta de fondos
payload = {
    "event_id": f"evt_{uuid.uuid4()}",
    "tenant_id": "org_12345",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "data": {
        "customer_id": "cus_999",
        "invoice_id": "in_555",
        "amount": 1500.50,
        "currency": "ARS",
        "error_code": "insufficient_funds",
        "attempt_count": 1
    }
}

# Convertimos a string para poder firmarlo exactamente igual que la pasarela
raw_body = json.dumps(payload).encode("utf-8")

# 3. Magia criptográfica: generamos la firma que tu API espera
signature = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

# 4. Disparamos a producción
headers = {
    "X-API-Key": API_KEY,
    "Stripe-Signature": signature,
    "Content-Type": "application/json"
}

print(f"Enviando evento a {API_URL}/webhook/ingest...")
response = httpx.post(f"{API_URL}/webhook/ingest", content=raw_body, headers=headers)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")