import os, requests
HF_RR_BASE  = os.getenv("HF_RR_BASE") or os.getenv("HF_EMB_BASE")
HF_TOKEN    = os.getenv("HF_TOKEN")
RR_TIMEOUT  = float(os.getenv("HF_RR_TIMEOUT_SECONDS", "60"))

def tei_rerank_scores(query:str, docs:list[str], raw:bool=True):
    body = {"query": query, "texts": docs, "raw_scores": raw}
    h = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(f"{HF_RR_BASE}/rerank", headers=h, json=body, timeout=RR_TIMEOUT)
    r.raise_for_status()   
    ranks = r.json()
    ranks.sort(key=lambda x: x["index"])
    return [float(x["score"]) for x in ranks]