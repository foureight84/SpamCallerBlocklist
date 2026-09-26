#!/usr/bin/env python3
"""
SpamCallerBlocklist Aggregator
Aggregates, normalizes, and filters spam caller numbers from official
federal feeds (FCC, FTC) and community blocklists.

Enforces strict NANP E.164 formatting and rolling TTL expiration to prevent
blocking reassigned or recycled numbers.
"""

import argparse
import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set

USER_AGENT = "SpamCallerBlocklist-Aggregator/1.0 (+https://github.com/SpamCallerBlocklist)"

NANP_PATTERN = re.compile(r"^\+1([2-9]\d{2})([2-9]\d{6})$")

COMMUNITY_SOURCES = [
    {
        "name": "community_ai_blocklist",
        "url": "https://raw.githubusercontent.com/Shalom-Karr/AI-Number-Blocklist/main/blacklist.txt",
    }
]


def load_env_file(filepath: str) -> Dict[str, str]:
    env = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env


def get_api_key() -> Optional[str]:
    # Check OS environment
    for var in ["FTC_API_KEY", "FCC_DONOTCALL_API_KEY", "DATA_GOV_API_KEY"]:
        if os.environ.get(var):
            return os.environ[var]

    # Check local .env in current and parent directories
    for path in [".env", "../.env", "../../.env"]:
        if os.path.exists(path):
            env_vars = load_env_file(path)
            for var in ["FTC_API_KEY", "FCC_DONOTCALL_API_KEY", "DATA_GOV_API_KEY"]:
                if var in env_vars:
                    return env_vars[var]
    return None


def normalize_number(raw: Any) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        candidate = "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        candidate = "+" + digits
    else:
        return None

    m = NANP_PATTERN.match(candidate)
    if not m:
        return None

    area_code, exchange_subscriber = m.groups()
    # Exclude reserved/special prefixes: 555, N11
    if area_code.endswith("11") or exchange_subscriber.startswith("555"):
        return None

    return candidate


def fetch_fcc_records(cutoff_iso: str, limit: int = 5000) -> Dict[str, Dict[str, Any]]:
    print(f"[*] Querying FCC Consumer Complaints SODA API (since {cutoff_iso})...")
    soql_where = f"issue='Unwanted Calls' AND ticket_created > '{cutoff_iso}' AND (caller_id_number != '' OR advertiser_business_phone_number != '')"
    encoded_where = urllib.parse.quote(soql_where)

    batch_size = min(1000, limit)
    offset = 0
    records: Dict[str, Dict[str, Any]] = {}

    while offset < limit:
        params = urllib.parse.urlencode({
            "$where": soql_where,
            "$order": "ticket_created DESC",
            "$limit": str(batch_size),
            "$offset": str(offset),
        })
        url = f"https://opendata.fcc.gov/resource/3xyp-aqkj.json?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[!] Warning: FCC query failed at offset {offset}: {e}", file=sys.stderr)
            break

        if not batch:
            break

        for item in batch:
            ticket_created = item.get("ticket_created")
            call_type = item.get("type_of_call_or_messge", "")
            cat = item.get("type_of_property_goods_or_services", "")

            for field in ["caller_id_number", "advertiser_business_phone_number"]:
                num = normalize_number(item.get(field))
                if num:
                    if num not in records:
                        records[num] = {
                            "report_count": 0,
                            "first_seen": ticket_created,
                            "last_seen": ticket_created,
                            "sources": set(["fcc"]),
                            "categories": set(),
                            "call_types": set(),
                        }
                    rec = records[num]
                    rec["report_count"] += 1
                    rec["sources"].add("fcc")
                    if ticket_created:
                        if not rec["first_seen"] or ticket_created < rec["first_seen"]:
                            rec["first_seen"] = ticket_created
                        if not rec["last_seen"] or ticket_created > rec["last_seen"]:
                            rec["last_seen"] = ticket_created
                    if cat:
                        rec["categories"].add(cat)
                    if call_type:
                        rec["call_types"].add(call_type)

        offset += len(batch)
        if len(batch) < batch_size:
            break

    print(f"    [+] Ingested {len(records)} unique valid E.164 numbers from FCC feed.")
    return records


def fetch_ftc_records(start_date_str: str, end_date_str: str, api_key: str, limit: int = 2000) -> Dict[str, Dict[str, Any]]:
    print(f"[*] Querying FTC Do Not Call Complaints API ({start_date_str} to {end_date_str})...")
    batch_size = 50
    offset = 0
    records: Dict[str, Dict[str, Any]] = {}

    while offset < limit:
        params = urllib.parse.urlencode({
            "created_date_from": f'"{start_date_str} 00:00:00"',
            "created_date_to": f'"{end_date_str} 23:59:59"',
            "items_per_page": str(batch_size),
            "offset": str(offset),
        })
        url = f"https://api.ftc.gov/v0/dnc-complaints?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "X-Api-Key": api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[!] Warning: FTC query failed at offset {offset}: {e}", file=sys.stderr)
            break

        data = payload.get("data", [])
        if not data:
            break

        for item in data:
            attrs = item.get("attributes", {})
            raw_num = attrs.get("company-phone-number")
            num = normalize_number(raw_num)
            if not num:
                continue

            created = attrs.get("created-date")
            is_robocall = attrs.get("recorded-message-or-robocall") == "Y"
            subject = attrs.get("subject", "")

            if num not in records:
                records[num] = {
                    "report_count": 0,
                    "first_seen": created,
                    "last_seen": created,
                    "sources": set(["ftc"]),
                    "categories": set(),
                    "call_types": set(),
                }
            rec = records[num]
            rec["report_count"] += 1
            rec["sources"].add("ftc")
            if created:
                if not rec["first_seen"] or created < rec["first_seen"]:
                    rec["first_seen"] = created
                if not rec["last_seen"] or created > rec["last_seen"]:
                    rec["last_seen"] = created
            if is_robocall:
                rec["call_types"].add("Robocall")
            if subject:
                rec["categories"].add(subject)

        offset += len(data)
        if len(data) < batch_size:
            break

    print(f"    [+] Ingested {len(records)} unique valid E.164 numbers from FTC feed.")
    return records


def fetch_community_records(source_info: Dict[str, str], current_iso: str) -> Dict[str, Dict[str, Any]]:
    name = source_info["name"]
    url = source_info["url"]
    print(f"[*] Querying community blocklist '{name}' from {url}...")
    records: Dict[str, Dict[str, Any]] = {}
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[!] Warning: Failed to fetch {name}: {e}", file=sys.stderr)
        return records

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        num = normalize_number(line)
        if num:
            records[num] = {
                "report_count": 1,
                "first_seen": current_iso,
                "last_seen": current_iso,
                "sources": set([name]),
                "categories": set(["Community Reported"]),
                "call_types": set(),
            }

    print(f"    [+] Ingested {len(records)} valid E.164 numbers from {name}.")
    return records


def aggregate_feeds(
    days: int = 30,
    output_dir: str = "dist",
    limit_fcc: int = 5000,
    limit_ftc: int = 2000,
    include_community: bool = True,
) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT00:00:00.000Z")
    start_date_str = cutoff.strftime("%Y-%m-%d")
    end_date_str = now.strftime("%Y-%m-%d")
    current_iso = now.isoformat()

    print(f"==================================================")
    print(f"SpamCallerBlocklist Aggregator Starting")
    print(f"Time: {current_iso}")
    print(f"Sliding TTL Window: {days} days (Cutoff: {start_date_str})")
    print(f"==================================================")

    aggregated: Dict[str, Dict[str, Any]] = {}

    def merge_records(incoming: Dict[str, Dict[str, Any]]):
        for num, meta in incoming.items():
            if num not in aggregated:
                aggregated[num] = meta
            else:
                existing = aggregated[num]
                existing["report_count"] += meta["report_count"]
                existing["sources"].update(meta["sources"])
                existing["categories"].update(meta["categories"])
                existing["call_types"].update(meta["call_types"])
                if meta.get("first_seen") and (not existing["first_seen"] or meta["first_seen"] < existing["first_seen"]):
                    existing["first_seen"] = meta["first_seen"]
                if meta.get("last_seen") and (not existing["last_seen"] or meta["last_seen"] > existing["last_seen"]):
                    existing["last_seen"] = meta["last_seen"]

    # 1. Fetch FCC
    try:
        fcc_data = fetch_fcc_records(cutoff_iso, limit=limit_fcc)
        merge_records(fcc_data)
    except Exception as e:
        print(f"[!] Error fetching FCC data: {e}", file=sys.stderr)

    # 2. Fetch FTC
    api_key = get_api_key()
    if api_key:
        try:
            ftc_data = fetch_ftc_records(start_date_str, end_date_str, api_key, limit=limit_ftc)
            merge_records(ftc_data)
        except Exception as e:
            print(f"[!] Error fetching FTC data: {e}", file=sys.stderr)
    else:
        print("[!] No FTC API key found (set FTC_API_KEY env). Skipping FTC feed.")

    # 3. Fetch Community Lists
    if include_community:
        for c_source in COMMUNITY_SOURCES:
            try:
                comm_data = fetch_community_records(c_source, current_iso)
                merge_records(comm_data)
            except Exception as e:
                print(f"[!] Error fetching community source {c_source['name']}: {e}", file=sys.stderr)

    # 4. Filter and Score
    # Score 2 = High confidence (multiple reports or multiple sources)
    # Score 1 = Single report / suspicious
    os.makedirs(output_dir, exist_ok=True)
    sorted_numbers = sorted(aggregated.keys())

    json_payload = {
        "metadata": {
            "title": "Spam Caller Blocklist",
            "generated_at": current_iso,
            "window_days": days,
            "total_active_numbers": len(sorted_numbers),
            "sources_included": sorted(list({s for rec in aggregated.values() for s in rec["sources"]})),
        },
        "numbers": {},
    }

    for num in sorted_numbers:
        meta = aggregated[num]
        sources = sorted(list(meta["sources"]))
        is_multi_source = len(sources) > 1
        is_multi_report = meta["report_count"] >= 2
        confidence_score = 2 if (is_multi_source or is_multi_report) else 1

        json_payload["numbers"][num] = {
            "score": confidence_score,
            "reports": meta["report_count"],
            "first_seen": meta["first_seen"],
            "last_seen": meta["last_seen"],
            "sources": sources,
            "call_types": sorted(list(meta["call_types"])),
            "categories": sorted(list(meta["categories"]))[:5],
        }

    # Write blocklist.txt (plain sorted list)
    txt_path = os.path.join(output_dir, "blocklist.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for num in sorted_numbers:
            f.write(f"{num}\n")

    # Write blocklist.txt.gz
    gz_path = os.path.join(output_dir, "blocklist.txt.gz")
    with gzip.open(gz_path, "wb") as f:
        for num in sorted_numbers:
            f.write(f"{num}\n".encode("utf-8"))

    # Write blocklist.json
    json_path = os.path.join(output_dir, "blocklist.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2)

    print(f"\n[+] Successfully generated blocklist outputs in '{output_dir}/':")
    print(f"    - {txt_path}: {len(sorted_numbers)} active numbers")
    print(f"    - {gz_path}: {os.path.getsize(gz_path):,} bytes (compressed)")
    print(f"    - {json_path}: {os.path.getsize(json_path):,} bytes (rich metadata)")


def main():
    parser = argparse.ArgumentParser(description="Aggregate and normalize spam caller blocklists.")
    parser.add_argument("--days", type=int, default=30, help="Sliding TTL window in days (default: 30)")
    parser.add_argument("--output-dir", type=str, default="dist", help="Output directory (default: dist)")
    parser.add_argument("--limit-fcc", type=int, default=5000, help="Max FCC records to ingest")
    parser.add_argument("--limit-ftc", type=int, default=2000, help="Max FTC records to ingest")
    parser.add_argument("--skip-community", action="store_true", help="Skip community blocklists")
    args = parser.parse_args()

    aggregate_feeds(
        days=args.days,
        output_dir=args.output_dir,
        limit_fcc=args.limit_fcc,
        limit_ftc=args.limit_ftc,
        include_community=not args.skip_community,
    )


if __name__ == "__main__":
    main()
