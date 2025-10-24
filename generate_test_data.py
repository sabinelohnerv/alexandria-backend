#!/usr/bin/env python
"""
Script para generar datos de prueba (consultas + feedback) vía API.
Requiere servidor Django corriendo en localhost:8000.

Uso:
    python generate_test_data.py --queries 20 --feedback-ratio 0.8
"""
import os
import sys
import argparse
import time
import requests
from typing import List, Dict, Optional

# Configuración
API_BASE = "http://localhost:8000/api"
DEFAULT_EMAIL = "test@adaptive.local"
DEFAULT_PASSWORD = "testpass123"

SAMPLE_QUERIES = [
    "¿Qué es el amparo constitucional?",
    "Jurisprudencia sobre TCP y derechos fundamentales",
    "Sentencias sobre derecho al trabajo",
    "¿Cuál es el procedimiento de amparo?",
    "Normativa sobre contratos laborales",
    "Derechos de la mujer en Bolivia",
    "Jurisprudencia sobre derecho a la salud",
    "¿Qué dice la CPE sobre educación?",
    "Sentencias sobre libertad de expresión",
    "Procedimiento administrativo sancionador",
    "Derechos de los pueblos indígenas",
    "Jurisprudencia sobre medio ambiente",
    "¿Qué es el debido proceso?",
    "Sentencias sobre derecho a la vivienda",
    "Normativa sobre seguridad social",
    "Derechos laborales en el sector público",
    "Jurisprudencia sobre libertad de prensa",
    "¿Qué es el control de constitucionalidad?",
    "Sentencias sobre derecho a la educación",
    "Normativa sobre protección al consumidor",
]

def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def get_jwt_token(email: str, password: str) -> Optional[str]:
    """Obtiene JWT token para autenticación."""
    print(f"Autenticando usuario: {email}")
    
    # Intentar login
    resp = requests.post(
        f"{API_BASE}/auth/login/",
        json={"email": email, "password": password}
    )
    
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access")
        print(f"✓ Token obtenido")
        return token
    
    # Si falla, intentar crear usuario
    print(f"Login falló, intentando crear usuario...")
    
    # Crear usuario (asumiendo endpoint de signup)
    resp = requests.post(
        f"{API_BASE}/auth/signup/request-otp/",
        json={"email": email}
    )
    
    if resp.status_code in [200, 201]:
        print(f"⚠ Usuario creado, pero necesitas verificar OTP manualmente")
        print(f"   Usa el script test_adaptive_ranking.py en su lugar")
        return None
    
    print(f"✗ No se pudo autenticar: {resp.status_code}")
    return None

def ask_query(token: str, query: str, session_id: Optional[int] = None) -> Optional[Dict]:
    """Envía una consulta al endpoint de búsqueda."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    
    resp = requests.post(f"{API_BASE}/search/ask", json=payload, headers=headers)
    
    if resp.status_code == 200:
        return resp.json()
    
    print(f"✗ Error en consulta: {resp.status_code} - {resp.text[:200]}")
    return None

def send_feedback(token: str, hit_id: int, label: str) -> bool:
    """Envía feedback para un hit."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"hit_id": hit_id, "label": label}
    
    resp = requests.post(f"{API_BASE}/search/feedback", json=payload, headers=headers)
    
    if resp.status_code in [200, 201]:
        return True
    
    print(f"✗ Error en feedback: {resp.status_code}")
    return False

def generate_queries(token: str, n: int) -> List[Dict]:
    """Genera n consultas y retorna los resultados."""
    print_section(f"GENERANDO {n} CONSULTAS")
    
    results = []
    session_id = None
    
    for i in range(n):
        query = SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)]
        print(f"[{i+1}/{n}] {query[:50]}...")
        
        result = ask_query(token, query, session_id)
        if result:
            msg = result.get("message", {})
            hits = result.get("hits", [])
            
            # Usar la misma sesión para todas las consultas
            if not session_id and msg.get("session"):
                session_id = msg["session"].get("id")
            
            print(f"    → Message ID: {msg.get('id')}, Hits: {len(hits)}")
            results.append(result)
        
        time.sleep(0.5)  # Rate limiting
    
    print(f"\n✓ Total consultas: {len(results)}")
    return results

def generate_feedback(token: str, results: List[Dict], ratio: float = 0.8):
    """Genera feedback contrastante para los resultados."""
    print_section(f"GENERANDO FEEDBACK (ratio={ratio})")
    
    stats = {"useful": 0, "not_useful": 0, "queries": 0}
    
    for result in results:
        hits = result.get("hits", [])
        if len(hits) < 2:
            continue
        
        # Decidir si enviar feedback para esta consulta
        import random
        if random.random() > ratio:
            continue
        
        # Feedback útil para el primer hit
        hit_useful = hits[0]
        if send_feedback(token, hit_useful["id"], "useful"):
            stats["useful"] += 1
            print(f"✓ Útil: hit {hit_useful['id']}")
        
        # Feedback no útil para el último hit
        hit_not_useful = hits[-1]
        if send_feedback(token, hit_not_useful["id"], "not_useful"):
            stats["not_useful"] += 1
            print(f"✓ No útil: hit {hit_not_useful['id']}")
        
        stats["queries"] += 1
        time.sleep(0.3)
    
    print(f"\n✓ Feedback enviado:")
    print(f"  - Útil: {stats['useful']}")
    print(f"  - No útil: {stats['not_useful']}")
    print(f"  - Consultas: {stats['queries']}")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Genera datos de prueba para Adaptive Ranking")
    parser.add_argument("--queries", type=int, default=20, help="Número de consultas a generar")
    parser.add_argument("--feedback-ratio", type=float, default=0.8, help="Ratio de consultas con feedback (0.0-1.0)")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Email del usuario")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password del usuario")
    parser.add_argument("--api-base", default=API_BASE, help="URL base de la API")
    
    args = parser.parse_args()
    
    global API_BASE
    API_BASE = args.api_base
    
    print_section("GENERADOR DE DATOS DE PRUEBA")
    print(f"API: {API_BASE}")
    print(f"Usuario: {args.email}")
    print(f"Consultas: {args.queries}")
    print(f"Feedback ratio: {args.feedback_ratio}")
    
    # Autenticar
    token = get_jwt_token(args.email, args.password)
    if not token:
        print("\n✗ No se pudo obtener token de autenticación")
        print("   Opciones:")
        print("   1. Crea el usuario manualmente en Django admin")
        print("   2. Usa el script test_adaptive_ranking.py (no requiere API)")
        sys.exit(1)
    
    # Generar consultas
    results = generate_queries(token, args.queries)
    if not results:
        print("\n✗ No se pudieron generar consultas")
        sys.exit(1)
    
    # Generar feedback
    stats = generate_feedback(token, results, args.feedback_ratio)
    
    print_section("COMPLETADO")
    print(f"✓ Consultas: {len(results)}")
    print(f"✓ Feedback útil: {stats['useful']}")
    print(f"✓ Feedback no útil: {stats['not_useful']}")
    print(f"\nAhora puedes:")
    print(f"  1. Validar ETL: python manage.py shell -c \"from ranking_adaptive.utils import build_pairwise_dataset; d=build_pairwise_dataset(); print(f'Pares: {{d.n_pairs}}')\"")
    print(f"  2. Entrenar: python manage.py shell -c \"from ranking_adaptive.tasks import train_signal_weights; print(train_signal_weights())\"")
    print(f"  3. Ver métricas: python manage.py report_adaptive_metrics --hours 24")

if __name__ == "__main__":
    main()
