import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()

# 🛡️ SecurityScorecard API Config
SSC_API_KEY = os.getenv("SSC_API_KEY")
SSC_PORTFOLIO_ID = os.getenv("SSC_PORTFOLIO_ID")
SSC_HEADERS = {"Authorization": f"Token {SSC_API_KEY}"}

# 📋 Monday.com API Config
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
MONDAY_HEADERS = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type": "application/json"
}
MONDAY_API_URL = "https://api.monday.com/v2"

# 📌 Your Board and Column IDs
BOARD_ID = os.getenv("MONDAY_BOARD_ID")
DOMAIN_COLUMN_ID = os.getenv("DOMAIN_COLUMN_ID")
SCORE_COLUMN_ID = os.getenv("SCORE_COLUMN_ID")
GRADE_COLUMN_ID = os.getenv("GRADE_COLUMN_ID")

# 🔁 Get SSC Scores
def get_ssc_scores():
    print("📡 Pulling score data from SecurityScorecard...")
    scored_companies = {}

    url = f"https://api.securityscorecard.io/portfolios/{SSC_PORTFOLIO_ID}/companies"
    params = {"limit": 500, "offset": 0}

    while True:
        response = requests.get(url, headers=SSC_HEADERS, params=params)
        if response.status_code != 200:
            print(f"❌ Failed to retrieve data from SSC: {response.status_code}")
            break

        data = response.json()
        if not data.get("entries"):
            break

        for entry in data["entries"]:
            domain = normalize_domain(entry.get("domain", ""))
            score = entry.get("score")
            grade = entry.get("grade")  # ✅ NEW
            if domain and score is not None and grade:
                scored_companies[domain] = {
                    "score": entry.get("score"),
                    "grade": entry.get("grade")
                }

        if "next" not in data.get("links", {}):
            break
        params["offset"] += 500

    print(f"✅ Retrieved {len(scored_companies)} scored companies from SSC")
    return scored_companies

# 🧼 Normalize domains for matching
def normalize_domain(domain):
    return domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]

# 🧠 Query Monday.com GraphQL
def monday_query(query, variables=None):
    response = requests.post(
        MONDAY_API_URL,
        headers=MONDAY_HEADERS,
        json={"query": query, "variables": variables}
    )
    if response.status_code != 200:
        raise Exception(f"❌ Monday API Error {response.status_code}: {response.text}")
    return response.json()

# 📋 Get all items from board
def get_all_board_items(board_id, domain_column_id):
    print("📋 Fetching all items from Monday.com board...")
    all_items = []
    cursor = None
    limit = 100

    while True:
        after = f', cursor: "{cursor}"' if cursor else ""
        query = f"""
        query {{
          boards(ids: {board_id}) {{
            items_page(limit: {limit}{after}) {{
              cursor
              items {{
                id
                name
                column_values(ids: ["{domain_column_id}"]) {{
                  id
                  text
                }}
              }}
            }}
          }}
        }}
        """

        result = monday_query(query)
        try:
            page = result["data"]["boards"][0]["items_page"]
            items = page["items"]
            cursor = page["cursor"]
        except Exception as e:
            print(f"❌ Failed to fetch items: {e}")
            print(json.dumps(result, indent=2))
            break

        for item in items:
            domain = None
            for cv in item["column_values"]:
                if cv["id"] == domain_column_id:
                    domain = normalize_domain(cv["text"]) if cv["text"] else None
            if domain:
                all_items.append({"id": item["id"], "name": item["name"], "domain": domain})

        if not cursor:
            break

    print(f"✅ Retrieved {len(all_items)} items from board")
    return all_items

# ✏️ Update score and grade in Monday.com
def update_score_and_grade(item_id, score, grade):
    query = f"""
    mutation {{
      updateScore: change_simple_column_value(
        board_id: {BOARD_ID},
        item_id: {item_id},
        column_id: "{SCORE_COLUMN_ID}",
        value: "{score}"
      ) {{
        id
      }}
      updateGrade: change_simple_column_value(
        board_id: {BOARD_ID},
        item_id: {item_id},
        column_id: "{GRADE_COLUMN_ID}",
        value: "{grade}"
      ) {{
        id
      }}
    }}
    """
    result = monday_query(query)
    return result.get("data")

# 🧠 Main Sync Logic
def main():
    ssc_data = get_ssc_scores()
    if not ssc_data:
        print("⚠️ No scored companies found. Exiting.")
        return

    monday_items = get_all_board_items(BOARD_ID, DOMAIN_COLUMN_ID)

    updated_count = 0
    skipped_count = 0

    for item in monday_items:
        domain = item["domain"]
        item_id = item["id"]

        if domain in ssc_data:
            score = ssc_data[domain]["score"]
            grade = ssc_data[domain]["grade"]
            update_score_and_grade(item_id, score, grade)
            print(f"✅ Updated {domain} with score {score} and grade {grade}")
            updated_count += 1
        else:
            print(f"⏩ Skipped {domain} (not in SSC scored list)")
            skipped_count += 1

    print(f"\n🔁 Sync complete: {updated_count} updated, {skipped_count} skipped")

if __name__ == "__main__":
    main()
