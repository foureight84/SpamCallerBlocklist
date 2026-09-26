# Spam Caller Blocklist

An automated, normalized, open-source spam caller blocklist aggregating official US federal regulatory datasets (FCC Unwanted Calls, FTC Do Not Call complaints) and open community sources.

Updated weekly via automated GitHub Actions with a **30-day sliding TTL window** to eliminate stale entries and protect reassigned numbers.

---

## Direct Downloads

| File | Description | Format |
| :--- | :--- | :--- |
| **[`dist/blocklist.txt`](dist/blocklist.txt)** | Plain sorted list of active numbers (one per line) | E.164 (`+1NXXNXXXXXX`) |
| **[`dist/blocklist.txt.gz`](dist/blocklist.txt.gz)** | Gzip-compressed list for low-bandwidth downloads | Gzip |
| **[`dist/blocklist.json`](dist/blocklist.json)** | Rich metadata including scores, dates, and categories | JSON |

Raw download URLs for direct curl / cron scripts:
```text
https://raw.githubusercontent.com/<OWNER>/SpamCallerBlocklist/main/dist/blocklist.txt
https://raw.githubusercontent.com/<OWNER>/SpamCallerBlocklist/main/dist/blocklist.json
https://raw.githubusercontent.com/<OWNER>/SpamCallerBlocklist/main/dist/blocklist.txt.gz
```

---

## Core Features & Design Principles

### 1. Strict NANP E.164 Normalization
All incoming raw complaint records are validated against North American Numbering Plan (NANP) standards:
* Validates 10-digit structure: `+1[2-9]XX[2-9]XXXXXX`.
* Rejects malformed records, corrupt text rows, `555` test numbers, and N11 emergency/service codes (e.g. 911, 411).

### 2. The 30-Day Carrier TTL (Preventing Reassigned Number Blocking)
VoIP autodialers and robocallers lease and abandon phone numbers rapidly, often within 48 to 72 hours. Telecom carriers hold disconnected numbers in a cooling pool before reassigning them to innocent subscribers or local businesses.

* Numbers that do not receive fresh complaints within a **30-day sliding window** automatically expire and are purged from the active blocklist.
* Eliminates the false-positive risk of blocking recycled phone numbers without requiring paid database lookups.

### 3. Confidence Scoring (`blocklist.json`)
Each entry in the metadata file includes a confidence score:
* **Score 2 (High Confidence):** Number was reported multiple times or appeared across multiple independent regulatory feeds within the 30-day window. Safe for automatic silent blocking.
* **Score 1 (Suspicious / Challenge):** Single recent complaint or present on community blocklists. Recommended for automated verification or screening challenges.

---

## Data Sources

1. **FCC Consumer Complaints Database (`opendata.fcc.gov`):**
   * Dataset: `3xyp-aqkj` (Unwanted Calls).
   * Updated nightly by the FCC Consumer and Governmental Affairs Bureau.
2. **FTC Do Not Call (DNC) Reported Calls API (`api.ftc.gov`):**
   * Endpoint: `/v0/dnc-complaints`.
   * Updated every weekday at noon ET with consumer robocall violation complaints.
3. **Verified Community Blocklists:**
   * Curated open-source autodialer and AI caller lists.

---

## Integration Examples

### Bash / Cron Lookup
```bash
# Download the latest blocklist once weekly
curl -s -O https://raw.githubusercontent.com/<OWNER>/SpamCallerBlocklist/main/dist/blocklist.txt

# Instant lookup using grep
CALLER="+18558810711"
if grep -Fxq "$CALLER" blocklist.txt; then
    echo "Blocked: $CALLER is on the spam blocklist"
fi
```

### Python Lookup
```python
import urllib.request

url = "https://raw.githubusercontent.com/<OWNER>/SpamCallerBlocklist/main/dist/blocklist.txt"
with urllib.request.urlopen(url) as resp:
    spam_set = set(resp.read().decode("utf-8").splitlines())

def is_spam(phone_number: str) -> bool:
    return phone_number in spam_set
```

---

## Local Setup & Development

### Requirements
* Python 3.9+ (Zero external dependencies; uses only Python standard library).

### Running the Aggregator Locally
```bash
# Clone the repository
git clone https://github.com/<OWNER>/SpamCallerBlocklist.git
cd SpamCallerBlocklist

# Run with FCC and Community sources (30-day window)
python3 scripts/aggregate.py --days 30 --output-dir dist

# Run with FTC API key included
export FTC_API_KEY="your_api_data_gov_key"
python3 scripts/aggregate.py --days 30 --output-dir dist
```

---

## License

This project aggregates public domain US government data (FCC, FTC) and open community blocklists. The code and workflows are licensed under the MIT License.
