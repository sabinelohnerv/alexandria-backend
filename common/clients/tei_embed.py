import os, requests, numpy as np
HF_BASE  = os.getenv("HF_EMB_BASE")
HF_TOKEN = os.getenv("HF_TOKEN")
TOUT     = float(os.getenv("HF_TIMEOUT_SECONDS", "60"))

def tei_embed(texts):
    h = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(f"{HF_BASE}/embed", headers=h, json={"inputs": list(texts)}, timeout=TOUT)
    r.raise_for_status()
    arr = np.array(r.json(), dtype=np.float32)
    n = np.linalg.norm(arr, axis=1, keepdims=True); n[n==0]=1
    return (arr/n).astype(np.float32, copy=False)
