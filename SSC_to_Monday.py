import os
from dotenv import load_dotenv
import requests
import json
import urllib.parse  # Used for safer URL/string handling

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
board_id = os.getenv("MONDAY_BOARD_ID")
domain_column_id = os.getenv("DOMAIN_COLUMN_ID")
score_column_id = os.getenv("SCORE_COLUMN_ID")
grade_column_id = os.getenv("GRADE_COLUMN_ID")

# --- VALIDATION BLOCK ---
try:
    if not board_id:
        raise ValueError("MONDAY_BOARD_ID is missing.")
    # Cast to int to ensure it's treated as a number
    board_id = int(board_id)
except (TypeError, ValueError) as e:
    raise ValueError(
        f"Error loading MONDAY_BOARD_ID: Must be a valid number. Check your .env file or environment variables.")

if not all([domain_column_id, score_column_id, grade_column_id]):
    raise ValueError("One or more required column IDs (DOMAIN, SCORE, GRADE) are missing.")


# --- END OF VALIDATION BLOCK ---

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
    if variables is None:
        variables = {}
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
        # Using GraphQL query with variables ($boardId, $limit, $cursor)
        query = """
        query GetBoardItems($boardId: [ID!], $limit: Int, $cursor: String) {
          boards(ids: $boardId) {
            items_page(limit: $limit, cursor: $cursor) {
              cursor
              items {
                id
                name
                column_values(ids: ["%s"]) {
                  id
                  text
                }
              }
            }
          }
        }
        """ % domain_column_id

        # Define the Python variables dictionary
        variables = {
            "boardId": [board_id],
            "limit": limit,
            "cursor": cursor
        }

        # Call monday_query with the variables
        result = monday_query(query, variables=variables)

        try:
            page = result["data"]["boards"][0]["items_page"]
            items = page["items"]
            cursor = page["cursor"]
        except Exception as e:
            # Enhanced error reporting for GraphQL errors
            if result.get("errors"):
                print(f"❌ Failed to fetch items: Monday API returned errors:")
                print(json.dumps(result["errors"], indent=2))
            else:
                print(f"❌ Failed to fetch items: {e}")
                print(json.dumps(result, indent=2))
            break

        for item in items:
            domain = None
            for cv in item["column_values"]:
                if cv["id"] == domain_column_id:
                    domain = normalize_domain(cv["text"]) if cv["text"] else None
            # IMPORTANT: Check if item["id"] is a valid number, skip if not
            try:
                item_id_int = int(item["id"])
            except ValueError:
                print(f"⚠️ Skipped item '{item.get('name', 'UNKNOWN')}' due to non-numeric item ID: {item['id']}")
                continue

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
        board_id: {board_id},
        item_id: {item_id},
        column_id: "{score_column_id}",
        value: "{score}"
      ) {{
        id
      }}
      updateGrade: change_simple_column_value(
        board_id: {board_id},
        item_id: {item_id},
        column_id: "{grade_column_id}",
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

    monday_items = get_all_board_items(board_id, domain_column_id)

    updated_count = 0
    skipped_count = 0

    for item in monday_items:
        domain = item["domain"]
        item_id = item["id"]

        # 🛑 FINAL SAFETY CHECK: Skip item if its ID is somehow invalid
        if not item_id or str(item_id).strip() == "":
            print(f"⏩ Skipped item with domain {domain} (missing item ID)")
            skipped_count += 1
            continue

        if domain in ssc_data:
            score = ssc_data[domain]["score"]
            grade = ssc_data[domain]["grade"]

            # 🛑 CHECK for valid SSC data
            if score is None or grade is None:
                print(f"⏩ Skipped {domain} (SSC score or grade data is missing)")
                skipped_count += 1
                continue

            update_score_and_grade(item_id, score, grade)
            print(f"✅ Updated {domain} with score {score} and grade {grade}")
            updated_count += 1
        else:
            print(f"⏩ Skipped {domain} (not in SSC scored list)")
            skipped_count += 1

    print(f"\n🔁 Sync complete: {updated_count} updated, {skipped_count} skipped")


if __name__ == "__main__":
    main()
