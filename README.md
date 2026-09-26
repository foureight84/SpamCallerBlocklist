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

## Data Sources & Citations

This blocklist aggregates and normalizes data from the following public regulatory and community sources:

### 1. Federal Communications Commission (FCC)
* **Agency:** US Federal Communications Commission (FCC) — Consumer and Governmental Affairs Bureau (CGB)
* **Dataset Title:** *Consumer Complaints Data: Unwanted Calls*
* **Dataset Identifier (Socrata 4x4 UID):** [`3xyp-aqkj`](https://opendata.fcc.gov/Consumer/CGB-Consumer-Complaints-Data/3xyp-aqkj)
* **API Documentation & Endpoint:** `https://opendata.fcc.gov/resource/3xyp-aqkj.json`
* **Query Filter:** `$where=issue='Unwanted Calls'`
* **Update Frequency:** Updated nightly.
* **Public Domain Notice:** United States Government Work (17 U.S.C. § 105; Public Domain).

### 2. Federal Trade Commission (FTC)
* **Agency:** US Federal Trade Commission (FTC)
* **Dataset Title:** *Do Not Call (DNC) Reported Calls Data API*
* **Developer Portal:** [FTC Developer Portal](https://www.ftc.gov/developer)
* **API Key Registration:** [api.data.gov Signup](https://api.data.gov/signup/)
* **API Endpoint:** `https://api.ftc.gov/v0/dnc-complaints`
* **Interactive Data Portal:** [FTC Explore Data (Do Not Call Data)](https://www.ftc.gov/exploredata)
* **Update Frequency:** Updated every business day at 12:00 PM ET.
* **Public Domain Notice:** United States Government Work (17 U.S.C. § 105; Public Domain).

### 3. Open-Source Community Lists
* **AI-Number-Blocklist:**
  * **Repository:** [Shalom-Karr/AI-Number-Blocklist](https://github.com/Shalom-Karr/AI-Number-Blocklist)
  * **Direct Feed:** `https://raw.githubusercontent.com/Shalom-Karr/AI-Number-Blocklist/main/blacklist.txt`
  * **Description:** Crowd-curated collection of phone numbers associated with automated AI voice bots, telemarketers, and autodialers.

### 4. Telephony Standards & Reference Authorities
* **Numbering Standard:** International Telecommunication Union (ITU-T E.164) & North American Numbering Plan Administrator (NANPA).
* **Validation Standard:** Strict NANP 10-digit validation (`+1[2-9]XX[2-9]XXXXXX`) rejecting unassigned area codes, 555 numbers, and N11 emergency/service codes.

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
