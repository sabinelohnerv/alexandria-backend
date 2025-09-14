import csv, re, os, argparse

def clean(in_path, out_path, year):
    fixed, total = 0, 0
    with open(in_path, newline="", encoding="utf-8") as inf, \
         open(out_path, "w", newline="", encoding="utf-8") as outf:
        rdr = csv.DictReader(inf)
        fields = ["storage_key","source_slug","authority","doc_type","number","year","published_date","title"]
        w = csv.DictWriter(outf, fieldnames=fields)
        w.writeheader()
        for row in rdr:
            total += 1
            key = (row.get("storage_key") or "").strip()

            # quitar prefijos "local/alexandria/" o "alexandria/"
            if key.startswith("local/alexandria/"):
                key = key[len("local/alexandria/"):]
            elif key.startswith("alexandria/"):
                key = key[len("alexandria/"):]
            
            # inferir source/authority/doc_type por la ruta
            source = (row.get("source_slug") or "").strip()
            auth   = (row.get("authority") or "").strip()
            doc_type = (row.get("doc_type") or "").strip()

            if "/tcp/" in key:
                source, auth = "tcp", "TCP"
            elif "/tsj/" in key:
                source, auth = "tsj", "TSJ"
                if not doc_type:
                    m = re.search(r"^raw/\d{4}/\d{2}/tsj/([^/]+)/", key)
                    cat = m.group(1) if m else ""
                    if   cat == "sentencias":     doc_type = "SENTENCIA"
                    elif cat == "resoluciones":   doc_type = "RESOLUCION"
                    elif cat == "autos_supremos": doc_type = "AUTO_SUPREMO"
            elif "/normativa/" in key:
                source, auth = "normativa", "LEG"
                if "/codigos/cpc/" in key and not doc_type:
                    doc_type = "CODE"
            else:
                source, auth = "tsj", "TSJ"  # fallback

            # número del nombre de archivo si no está
            number = (row.get("number") or "").strip()
            if not number:
                m = re.search(r"\d+", os.path.basename(key))
                if m: number = m.group(0)

            w.writerow({
                "storage_key": key,
                "source_slug": source,
                "authority": auth,
                "doc_type": doc_type,
                "number": number,
                "year": (row.get("year") or str(year)).strip(),
                "published_date": (row.get("published_date") or "").strip(),
                "title": (row.get("title") or "").strip(),
            })
            fixed += 1
    print(f"cleaned {fixed}/{total} rows -> {out_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="in_path",  required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()
    clean(args.in_path, args.out_path, args.year)
