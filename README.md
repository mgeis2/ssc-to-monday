# 🔄**SecurityScorecard to Monday.com Sync Script**
This Python script automatically syncs SecurityScorecard (SSC) scores and grades to a Monday.com board. It retrieves the latest scores for domains in a specific SSC portfolio and updates matching items in Monday.com based on domain name.

## 📁 **Features**
+ ✅ Fetches up to 500 scored domains from a SecurityScorecard portfolio

+ 🔍 Matches domains from SSC with those listed on a Monday.com board

+ ✏️ Updates numeric score and letter grade columns on matching Monday.com items

+ 🔁 Supports pagination for large boards and portfolios

## 📦 Requirements
+ Python 3.7+
+ requests
+ python-dotenv

Create a requirements.txt if you don't have one yet:
```
requests
python-dotenv
```

Install dependencies:
```
pip install -r requirements.txt
```

## 🔐 **Environment Variables**
Create a .env file in the project root with the following variables:


```
#SecurityScorecard API
SSC_API_KEY=your_ssc_api_key
SSC_PORTFOLIO_ID=your_portfolio_id

#Monday.com API
MONDAY_API_KEY=your_monday_api_key
MONDAY_BOARD_ID=123456789

#Column IDs from Monday.com
DOMAIN_COLUMN_ID=domain_column_id
SCORE_COLUMN_ID=numeric_column_id
GRADE_COLUMN_ID=text_or_status_column_id
```

You can get these values from:
+ SecurityScorecard: [API Docs](https://api.securityscorecard.io/)
+ Monday.com: Use the [API playground](https://api.monday.com/) to find board and column IDs.

## 🚀 **How to Run**

```
python Get\ Vendor\ Scores.py
```

## 📝 **Notes**
The script uses normalized domains to match (stripped of http(s)://, trailing slashes, etc.).

Only domains that exist in both SSC and Monday.com will be updated.

Items without a score or grade in SSC are skipped.
