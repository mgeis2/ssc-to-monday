import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# API Keys and constants
SSC_API_KEY = os.environ.get("SSC_API_KEY")
SSC_PORTFOLIO_ID = os.environ.get("SSC_PORTFOLIO_ID")  # Make sure this is set!
MONDAY_API_KEY = os.environ.get("MONDAY_API_KEY")

SSC_BASE_URL = "https://api.securityscorecard.io"
MONDAY_API_URL = "https://api.monday.com/v2"

BOARD_ID = 7436409221
DOMAIN_COLUMN_ID = "short_text7__1"
SCORE_COLUMN_ID = "text_mkqf6dzd"
GRADE_COLUMN_ID = "text_mkqf1dky"


class MondayAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

    def query(self, query_string):
        try:
            response = requests.post(
                MONDAY_API_URL,
                headers=self.headers,
                json={"query": query_string}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Monday API request failed: {e}")
            return {}


def normalize_domain(domain):
    """Strip whitespace and leading/trailing single quotes from domain."""
    if not domain:
        return None
    domain = domain.strip().strip("'").strip()
    # Remove URL schema if present
    if domain.startswith("http://"):
        domain = domain[len("http://"):]
    elif domain.startswith("https://"):
        domain = domain[len("https://"):]
    # Remove trailing slashes
    domain = domain.rstrip('/')
    return domain.lower()


def get_score_data():
    """Fetch companies from portfolio and then get scores per domain."""
    url = f"{SSC_BASE_URL}/portfolios/{SSC_PORTFOLIO_ID}/companies"
    headers = {
        "Authorization": f"Token {SSC_API_KEY}",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to get portfolio companies: {e}")
        return {}

    companies = response.json().get("entries", [])
    score_data = {}

    for company in companies:
        domain_raw = company.get("domain")
        domain = normalize_domain(domain_raw)
        company_name = company.get("name")

        if not domain:
            continue

        score_url = f"{SSC_BASE_URL}/companies/{domain}/scores"
        try:
            score_resp = requests.get(score_url, headers=headers)
            if score_resp.status_code == 200:
                score_info = score_resp.json()
                #print(f"DEBUG: Score response for domain '{domain}': {json.dumps(score_info, indent=2)}")

                #overall = score_info.get("overall", {})
                score = score_info.get("score")
                grade = score_info.get("grade")

                if score is not None and grade:
                    score_data[domain] = {
                        "name": company_name,
                        "score": score,
                        "grade": grade
                    }
                else:
                    print(f"⚠️ Score or grade missing in API for domain: {domain}")
            else:
                print(f"❌ Failed to fetch score for domain: {domain} (status {score_resp.status_code})")
        except requests.RequestException as e:
            print(f"❌ Error fetching score for domain {domain}: {e}")

    return score_data



def get_items_from_group(monday, board_id, group_id, domain_column_id):
    """Retrieve all items from a Monday.com group with pagination."""
    all_items = []
    cursor = None
    limit = 50

    while True:
        if cursor:
            after_clause = f'(limit: {limit}, cursor: {json.dumps(cursor)})'
        else:
            after_clause = f'(limit: {limit})'

        query = f"""
        query {{
          boards(ids: [{board_id}]) {{
            groups(ids: ["{group_id}"]) {{
              items_page{after_clause} {{
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
        }}
        """

        response = monday.query(query)

        try:
            group_data = response["data"]["boards"][0]["groups"][0]["items_page"]
            items = group_data["items"]
            prev_cursor = cursor
            cursor = group_data["cursor"]
            print(f"Group {group_id}: Retrieved {len(items)} items; cursor changed from {prev_cursor} to {cursor}")
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing items from group {group_id}: {e}")
            break

        for item in items:
            domain = None
            for col in item.get("column_values", []):
                if col["id"] == domain_column_id:
                    domain = col.get("text")
                    domain = normalize_domain(domain)
                    break
            if domain:
                all_items.append({
                    "id": item["id"],
                    "name": item["name"],
                    "domain": domain
                })

        if not cursor:
            print(f"Group {group_id}: No more pages.")
            break

        if cursor == prev_cursor:
            print(f"Group {group_id}: Cursor did not advance, stopping to avoid infinite loop.")
            break

    return all_items


def get_all_board_groups(monday, board_id):
    """Get all group IDs and titles for a Monday.com board."""
    query = f"""
    query {{
      boards(ids: [{board_id}]) {{
        groups {{
          id
          title
        }}
      }}
    }}
    """
    response = monday.query(query)
    try:
        groups = response["data"]["boards"][0]["groups"]
        return groups
    except (KeyError, IndexError, TypeError):
        print("Error fetching board groups")
        return []


def update_monday_item(monday, item_id, score, grade):
    """Update score and grade for a Monday.com item."""
    column_values = {
        SCORE_COLUMN_ID: str(score),
        GRADE_COLUMN_ID: grade
    }
    column_values_json = json.dumps(column_values).replace('"', '\\"')

    mutation = f"""
    mutation {{
      change_multiple_column_values(
        item_id: {item_id},
        board_id: {BOARD_ID},
        column_values: "{column_values_json}"
      ) {{
        id
      }}
    }}
    """
    response = monday.query(mutation)
    if response.get("data", {}).get("change_multiple_column_values"):
        print(f"✅ Updated item {item_id} with score: {score}, grade: {grade}")
        return True
    else:
        print(f"❌ Failed to update item {item_id}. Response: {response}")
        return False


def main():
    if not SSC_API_KEY or not MONDAY_API_KEY or not SSC_PORTFOLIO_ID:
        print("ERROR: Missing SSC_API_KEY, MONDAY_API_KEY, or SSC_PORTFOLIO_ID.")
        return

    monday = MondayAPI(MONDAY_API_KEY)

    print("Fetching all groups from Monday.com board...")
    groups = get_all_board_groups(monday, BOARD_ID)
    if not groups:
        print("No groups found or failed to fetch groups.")
        return

    print(f"Found {len(groups)} groups on board.")

    # Collect all items with domains across all groups
    all_items = []
    for group in groups:
        group_id = group["id"]
        group_title = group.get("title", "Unknown")
        print(f"Fetching items from group: {group_title} (ID: {group_id})")
        items = get_items_from_group(monday, BOARD_ID, group_id, DOMAIN_COLUMN_ID)
        all_items.extend(items)

    print(f"Total items with domains retrieved: {len(all_items)}")

    # Fetch scores from SecurityScorecard portfolio + individual score calls
    print("Fetching score data from SecurityScorecard portfolio...")
    scores = get_score_data()

    print(f"Total domains with score data retrieved: {len(scores)}")

    # For each Monday.com item, update if score data found
    for item in all_items:
        domain = item["domain"]
        if domain not in scores:
            print(f"⚠️ Missing score or grade for domain: {domain}")
            continue

        data = scores[domain]
        score = data.get("score")
        grade = data.get("grade")

        if score is None or not grade:
            print(f"⚠️ Score or grade missing in API for domain: {domain}")
            continue

        update_monday_item(monday, item["id"], score, grade)


if __name__ == "__main__":
    main()
