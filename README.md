#  ROOFING WORK ORDER Data Extraction (Assignment Submission)

## Overview
This project extracts structured JSON data from roofing work-order PDF using **Google Gemini API** and **Pydantic schema validation**.

It follows the assignment guidelines to ensure:
- Strict schema compliance  
- "None" for missing/unavailable fields  
- OOP-based dynamic prompt generation  
---

## Files
- `roofing_work_order.py` — Main extraction script  
- `99907349 Roof 3-redacted-output.json` — Extracted JSON sample output  
- `report.pdf` — Brief report (approach, challenges, results)  
- `99907349 Roof 3-redacted.pdf` — Contains the test case PDF  

---

## Requirements
- Python 3.10+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
- Add your Gemini API key to .env file:
  ```bash
  GOOGLE_API_KEY=your_api_key_here
- Run the Script:
  ```bash
  python roofing_work_order.py
