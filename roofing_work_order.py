"""
roofing_work_order.py
Implements structured data extraction from roofing work-order PDF using the Gemini API and Pydantic schema validation.
Features:
- OOP-based dynamic prompt construction
- Schema-compliant JSON output
- "None" for missing or unavailable fields
- Normalization and validation using Pydantic models
"""

import os
import json
import fitz  # PyMuPDF
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Optional
from pydantic import BaseModel, ValidationError


# ---------------------------
# 1) Pydantic Schema
# ---------------------------

class Party(BaseModel):
    name: Optional[str] = "None"
    address1: Optional[str] = "None"
    address2: Optional[str] = "None"
    address3: Optional[str] = "None"
    city: Optional[str] = "None"
    state: Optional[str] = "None"
    country: Optional[str] = "None"
    country_code: Optional[str] = "None"
    zip: Optional[str] = "None"


class Contact(BaseModel):
    name: Optional[str] = "None"
    email: Optional[str] = "None"
    contact_number: Optional[str] = "None"


class Header(BaseModel):
    ship_to: Party
    bill_to: Party
    vendor: Optional[Party] = "None"
    buyer_contact: Contact
    shipping_contact: Contact
    project_number: Optional[str] = "None"
    purchase_order_number: Optional[str] = "None"
    job_name: Optional[str] = "None"
    job_number: Optional[str] = "None"
    quote_number: Optional[str] = "None"
    date_ordered: Optional[str] = "None"
    delivery_date: Optional[str] = "None"
    shipping_instructions: Optional[str] = "None"
    notes: Optional[str] = "None"
    ship_via: Optional[str] = "None"
    payment_terms: Optional[str] = "None"


class LineItem(BaseModel):
    line_no: Optional[str] = "None"
    on_hand: Optional[str] = "None"
    to_buy: Optional[str] = "None"
    quantity: Optional[int] = "None"
    uom: Optional[str] = "None"
    unit_price: Optional[str] = "None"
    currency: Optional[str] = "None"
    part_numbers: Optional[str] = "None"
    product_description: Optional[str] = "None"
    spell_corrected_product_description: Optional[str] = "None"


class ExtractionItem(BaseModel):
    header: Header
    line_items: List[LineItem]


class RootSchema(BaseModel):
    extraction: List[ExtractionItem]


# ---------------------------
# 2) Prompt Builder with Smart Field Hints
# ---------------------------

class FieldHint:
    def __init__(self, path: str, hint: str):
        self.path = path
        self.hint = hint


class PromptBuilder:
    BASE_RULES = (
        "You are an expert data extraction model. Extract all fields from a roofing work-order PDF into valid JSON.\n"
        "- Use contextual clues (like proximity or headers) to populate fields, even if not explicitly labeled.\n"
        "- Do NOT fabricate values. Use only information visible in the text.\n"
        "- If a field is missing or unreadable, return the literal string \"None\".\n"
        "- Preserve all numeric fields as strings if unsure, but prefer integer for quantities.\n"
        "- Dates must be in YYYY-MM-DD format if detected; otherwise use \"None\".\n"
        "- Return ONLY valid JSON matching this structure:\n"
        "{ \"extraction\": [ { \"header\": {...}, \"line_items\": [...] } ] }\n"
    )

    def __init__(self):
        self.field_hints: List[FieldHint] = []

    def add_hint(self, path: str, hint: str):
        self.field_hints.append(FieldHint(path, hint))

    def build(self, pdf_text: str) -> str:
        hint_lines = "\n".join([f"- {h.path}: {h.hint}" for h in self.field_hints])
        return (
            self.BASE_RULES
            + "\nField-Level Hints:\n"
            + hint_lines
            + "\n\nPDF_TEXT START\n"
            + pdf_text.strip()
            + "\nPDF_TEXT END\n\nRETURN: Valid JSON only."
        )


def build_final_prompt(pdf_text: str) -> str:
    pb = PromptBuilder()

    # Header hints
    pb.add_hint("header.job_number", "Use 'WO #' or similar as job_number.")
    pb.add_hint("header.date_ordered", "Extract from 'Start Date' or similar label.")
    pb.add_hint("header.delivery_date", "Extract from 'Delivery Date'")
    pb.add_hint("header.bill_to.name", "Customer or company name only (exclude address numbers).")
    pb.add_hint("header.bill_to.address1", "Street number and name of the billing address (e.g., '89 streetsman').")
    pb.add_hint("header.bill_to.city", "City associated with billing address.")
    pb.add_hint("header.bill_to.state", "State abbreviation (like PN, GA, etc.).")
    pb.add_hint("header.bill_to.zip", "Numeric ZIP code, even if short (e.g., '98').")
    pb.add_hint("header.ship_to", "If separate shipping section is not found, use same details as bill_to.")
    pb.add_hint("header.buyer_contact.name", "Name of project consultant or manager.")
    pb.add_hint("header.buyer_contact.contact_number", "Phone number of the consultant or manager.")
    pb.add_hint("header.shipping_contact.name", "Contact responsible for delivery/shipping if mentioned.")
    pb.add_hint("header.shipping_instructions", "Include all crew and delivery-related notes and instructions.")

    # Line items
    pb.add_hint("line_items", "Extract every material line (e.g., taps, buckets, ring) as a separate entry.")
    pb.add_hint("line_items.quantity", "Numeric quantity preceding item name; round decimals if needed.")
    pb.add_hint("line_items.product_description", "Full product/material description.")
    pb.add_hint("line_items.spell_corrected_product_description", "Same as description, corrected if typos exist.")

    return pb.build(pdf_text)


# ---------------------------
# 3) PDF Text Extraction + Gemini API
# ---------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from the PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    doc.close()
    return text.strip()


def call_gemini(prompt: str) -> str:
    """Call Gemini model with forced JSON output."""
    try:
        model = genai.GenerativeModel("models/gemini-2.5-pro")
    except Exception:
        model = genai.GenerativeModel("models/gemini-2.5-flash")

    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    return response.text


# ---------------------------
# 4) Normalize Gemini Output
# ---------------------------

def normalize_gemini_output(data: dict) -> dict:
    """Ensure valid structure and fill only missing sections."""
    if "extraction" not in data:
        data = {"extraction": [data]}

    header = data["extraction"][0].get("header", {})

    # Only fill missing fields; never overwrite model data
    def ensure_party(name):
        return {
            k: "None" for k in [
                "name", "address1", "address2", "address3",
                "city", "state", "country", "country_code", "zip"
            ]
        }

    if "ship_to" not in header:
        header["ship_to"] = ensure_party("ship_to")
    if "bill_to" not in header:
        header["bill_to"] = ensure_party("bill_to")
    if "buyer_contact" not in header:
        header["buyer_contact"] = {"name": "None", "email": "None", "contact_number": "None"}
    if "shipping_contact" not in header:
        header["shipping_contact"] = {"name": "None", "email": "None", "contact_number": "None"}

    # Normalize quantities
    for li in data["extraction"][0].get("line_items", []):
        q = li.get("quantity")
        if q is None:
            li["quantity"] = 0
        else:
            try:
                li["quantity"] = int(float(q))
            except Exception:
                li["quantity"] = 0

    return data


# ---------------------------
# 5) Main Runner
# ---------------------------

def main():
    load_dotenv()
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

    pdf_path = "99907349 Roof 3-redacted.pdf"
    pdf_text = extract_text_from_pdf(pdf_path)
    prompt = build_final_prompt(pdf_text)

    print("🚀 Sending prompt to Gemini...")
    llm_output = call_gemini(prompt)

    try:
        data = json.loads(llm_output)
        data = normalize_gemini_output(data)
        validated = RootSchema.model_validate(data)

        print("✅ Extraction Successful!\n")
        print(json.dumps(validated.model_dump(), indent=2, ensure_ascii=False))

        with open("roof_order_output.json", "w", encoding="utf-8") as f:
            json.dump(validated.model_dump(), f, indent=2, ensure_ascii=False)

        print("\n💾 Saved to roofing_work_order_output.json")

    except (json.JSONDecodeError, ValidationError) as e:
        print("❌ Error parsing/validating JSON:\n", e)
        print("\nRaw Output:\n", llm_output)


if __name__ == "__main__":
    main()

