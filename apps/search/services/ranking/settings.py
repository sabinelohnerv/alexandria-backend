from django.conf import settings

# Defaults
RANK_WEIGHTS_DEFAULT = {
    "W_CE": 1.0, "W_VIG": 0.75, "W_ORG": 0.35, "W_ID": 0.90, "W_T": 0.25,
}

ORG_WEIGHTS_DEFAULT = {
    "tcp": 1.0, "TCP": 1.0, "tsj": 0.8, "TSJ": 0.8, "sala": 0.6, "SALA": 0.6,
    "ley": 0.7, "LEY": 0.7, "cpe": 0.9, "CPE": 0.9, "alp": 0.7, "ALP": 0.7,
    "otros": 0.3, "OTROS": 0.3,
}

RECENCY_SOURCES_DEFAULT = {"tcp", "tsj", "sala"}
RECENCY_HALFLIFE_DAYS_DEFAULT = 4 * 365  # ≈ 4 años

ADAPTIVE_VECTOR_MODE = True

DEFAULTS = {
    "SEARCH_TOP_K": 24,
    "FUSION_CANDIDATES": 60,
    "RRF_K": 60.0,
    "RERANK_CANDIDATES": 30,  
    "MAX_RERANK_CHARS": 900,   
    "RERANK_TOP_N": 10,
    "RERANK_DOC_CAP": 2,
    "RERANK_BATCH_SIZE": 16,     
    "ENABLE_RERANK": True,
    "ENABLE_MMR": True,          
    "MMR_K": 4,                  
    "MMR_LAMBDA": 0.7,
    "LLM_PROVIDER": "together",
    "TOGETHER_MODEL": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "TOGETHER_MAX_TOKENS": 512,
    "TOGETHER_TEMPERATURE": 0.2,
    "TOGETHER_TOP_P": 1.0,
    "TOGETHER_FREQUENCY_PENALTY": 0.0,
    "TOGETHER_PRESENCE_PENALTY": 0.0,
    "LEXICAL_CANDIDATE_CAP": 1000,
    "HNSW_EF_SEARCH": 80,       
    "IVFFLAT_PROBES": 16,
    "TEI_WORKERS": 2,        
    "TEI_SHARD_SIZE": 12,    
}

def get_setting(name: str, default=None):
    if default is None:
        default = DEFAULTS.get(name)
    return getattr(settings, name, default)
