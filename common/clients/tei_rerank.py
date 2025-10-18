import os, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HF_RR_BASE  = os.getenv("HF_RR_BASE")
HF_TOKEN    = os.getenv("HF_TOKEN")
RR_TIMEOUT  = float(os.getenv("HF_RR_TIMEOUT_SECONDS", "30")) 

_session = requests.Session()
_session.headers.update({
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
    "Connection": "keep-alive",
})
_adapter = HTTPAdapter(
    pool_connections=32,
    pool_maxsize=64,
    max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504]),
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

def tei_rerank_scores(query: str, docs: list[str], raw: bool = True):
    total_chars = sum(len(d or "") for d in docs)
    body = {"query": query, "texts": docs, "raw_scores": raw}
    r = _session.post(f"{HF_RR_BASE}/rerank", json=body, timeout=RR_TIMEOUT)
    r.raise_for_status()
    ranks = r.json()
    ranks.sort(key=lambda x: x["index"])
    return [float(x["score"]) for x in ranks]
