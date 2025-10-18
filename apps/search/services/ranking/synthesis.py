from typing import List, Tuple, Dict, Any, Optional
from apps.documents.models import Chunk

def synthesize_answer(query: str,
                      hits: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any]]],
                      max_snippets: int = 5) -> Dict[str, Any]:
    """
    hits: [(chunk, score_base, {"vec","lex"}, score_rerank, final_score, signals)]
    """
    snippets = []
    for i, (ch, s_base, extra, s_rr, s_final, signals) in enumerate(hits[:max_snippets], start=1):
        src = (ch.document.source_slug or "").upper() if getattr(ch.document, "source_slug", None) else ""
        title = ch.document.title or f"{src} {ch.document.number or ''}".strip()
        preview = (ch.text or "")[:360].replace("\n", " ").strip()
        snippets.append({
            "rank": i,
            "document_id": ch.document_id,
            "chunk_id": ch.id,
            "title": title,
            "section": ch.section,
            "preview": preview,
            "similarity": round(float(extra.get("vec", 0.0)), 4),
            "lexical": round(float(extra.get("lex", 0.0)), 4) if extra.get("lex") is not None else None,
            "base": round(float(s_base), 4),
            "rerank": (round(float(s_rr), 4) if s_rr is not None else None),
            "final": round(float(s_final), 4),
            "signals": {
                "vigente": bool(signals.get("vigente")),
                "peso_org": round(float(signals.get("peso_org", 0.0)), 3),
                "match_id": bool(signals.get("match_id")),
                "recencia": round(float(signals.get("recencia", 0.0)), 3),
            }
        })

    lines = [f"Consulta: {query}", "", "Pasajes relevantes:"]
    for s in snippets:
        badges = []
        if s["signals"]["vigente"]:
            badges.append("vigente")
        if s["signals"]["match_id"]:
            badges.append("ID exacto")
        if s["signals"]["peso_org"] > 0:
            badges.append(f"órg={s['signals']['peso_org']}")
        if s["signals"]["recencia"] > 0:
            badges.append(f"t={s['signals']['recencia']}")
        extras = []
        extras.append(f"base={s['base']}")
        if s["rerank"] is not None:
            extras.append(f"ce={s['rerank']}")
        extras.append(f"final={s['final']}")
        lines.append(f"- {s['title']} [{s['section'] or 'BODY'}] ({', '.join(extras)} | {'; '.join(badges)}) — {s['preview']}")

    return {"text": "\n".join(lines), "snippets": snippets}
