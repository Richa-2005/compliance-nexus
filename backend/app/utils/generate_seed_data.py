from app.utils.pdf_generator import generate_compliance_pdf
from app.agents.audit_graph import audit_graph
from app.core.config import settings
import json
import os

query_data = [
    "Verify if a technology software licensing transaction of $1,800,000 USD initiated by Nexus India to an overseas vendor violates internal cross-border limits.",
    "Audit an outbound technology software fee remittance of $400,000 USD from Nexus India to an authorized overseas vendor under the single-transaction licensing ceiling.",
    "Review a $750,000 USD cross-border wire transfer from Nexus India to a newly onboarded overseas supplier where beneficiary KYC and originator information must be verified.",
    "Audit a $250,000 USD operational advance from Nexus India to an active vendor where a Nexus Holdings executive director owns a 3.1% promoter stake.",
    "Verify if a $12,500,000 USD equity capital remittance from Nexus India to acquire 45% of an overseas payment-processing fintech subsidiary requires approval-route treatment.",
    "Verify an outbound cloud infrastructure service fee remittance of $150,000 USD from Nexus India to AWS US East region.",
    "Audit an outbound software consultancy payment of $850,000 USD to a foreign vendor when cumulative quarterly technology remittances have already reached $4,600,000 USD.",
    "Evaluate a cross-border cryptocurrency treasury transfer of $900,000 USD initiated by Nexus Global to an anonymous offshore digital wallet with no verified beneficiary identity."
]

idx = 1
OUTPUT_FILE = settings.DB_DIR / "certificates"
SEED_DATA = settings.DB_DIR / "seed_data.json"
OUTPUT_FILE.mkdir(parents=True, exist_ok=True)

seed_start = max(int(os.getenv("SEED_START", "1")), 1)
seed_limit = int(os.getenv("SEED_LIMIT", str(len(query_data))))
seed_end = min(seed_start + seed_limit - 1, len(query_data))
target_indexes = set(range(seed_start, seed_end + 1))

existing_records = []
if SEED_DATA.exists():
    with open(SEED_DATA, "r", encoding="utf-8") as file:
        existing_records = json.load(file)
records_by_id = {
    record.get("transaction_id"): record
    for record in existing_records
    if record.get("transaction_id")
}

for old_pdf in OUTPUT_FILE.glob("TX_100*.pdf"):
    try:
        pdf_index = int(old_pdf.stem.replace("TX_100", ""))
    except ValueError:
        continue
    if pdf_index in target_indexes:
        old_pdf.unlink()

for query in query_data:
    transaction_id = f"TX_100{idx}"
    if idx not in target_indexes:
        idx += 1
        continue
    print(f"{transaction_id}")
    idx += 1
    
    graph_output = audit_graph.invoke({"query":query})
    output_file =  f"{OUTPUT_FILE}/{transaction_id}.pdf"
    file_path = generate_compliance_pdf(graph_output,output_file)

    final_data = {
        "transaction_id" : transaction_id,
        "query" : query,
        "transaction_value" : graph_output["extracted_metrics"].get("transaction_value",0.0),
        "allowed_ceiling" : graph_output["extracted_metrics"].get("allowed_ceiling",0.0),
        "source_doc" : graph_output["extracted_metrics"].get("source_doc",""),
        "audit_verdict_markdown" : graph_output["audit_verdict"],
        "citations_json" : json.dumps(graph_output["citations"]),
        "evidence_items": graph_output.get("evidence_items", []),
        "selected_evidence_items": graph_output.get("selected_evidence_items", []),
        "audit_checks": graph_output.get("audit_checks", []),
        "audit_rationale": graph_output.get("audit_rationale", {}),
        "pdf_path" : f"certificates/{transaction_id}.pdf"
    }

    check_results = {check.get("result") for check in final_data["audit_checks"]}
    if "FAIL" in check_results:
        final_data["state"] = "NON_COMPLIANT"
    elif "REVIEW" in check_results:
        final_data["state"] = "ACTION_REQUIRED"
    elif final_data["source_doc"] == "":
        final_data["state"] = "ACTION_REQUIRED"
    elif final_data["transaction_value"] > final_data["allowed_ceiling"] : 
        final_data["state"] = "NON_COMPLIANT"
    else:
        final_data["state"] = "COMPLIANT"


    records_by_id[transaction_id] = final_data
    
records = [
    records_by_id[f"TX_100{record_idx}"]
    for record_idx in range(1, len(query_data) + 1)
    if f"TX_100{record_idx}" in records_by_id
]

with open(SEED_DATA, "w", encoding="utf-8") as file:
    json.dump(records,file,indent=4)
    
    
