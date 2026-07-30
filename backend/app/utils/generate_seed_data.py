from app.utils.pdf_generator import generate_compliance_pdf
from app.agents.audit_graph import audit_graph
from app.core.config import settings
import json

query_data = [
    "Verify if a technology software licensing transaction of $1,800,000 USD initiated by Nexus India violates internal cross-border limits.",
    "Audit an outbound technology software fee remittance of $400,000 USD from Nexus India to an authorized vendor.",
    "Verify cross-border dividend remittance of $2,500,000 USD from foreign entity.",
    "Audit an outbound royalty fee payment of $650,000 USD initiated by Nexus Tech India to an overseas parent entity for proprietary intellectual property licensing.",
    "Evaluate a cross-border cryptocurrency treasury transfer of $900,000 USD initiated by Nexus Global to an anonymous offshore digital wallet.",
    "Verify an outbound cloud infrastructure service fee remittance of $150,000 USD from Nexus India to AWS US East region.",
    "Audit an outbound software consultancy payment of $850,000 USD to a foreign vendor when cumulative quarterly remittances for professional services have reached $2,100,000 USD.",
    "Verify if a cross-border equity capital remittance of $4,500,000 USD initiated by Nexus India to acquire an overseas fintech subsidiary violates authorized dealer approval thresholds."
]

idx = 1
OUTPUT_FILE = settings.DB_DIR / "certificates"
SEED_DATA = settings.DB_DIR / "seed_data.json"
OUTPUT_FILE.mkdir(parents=True, exist_ok=True)

for old_pdf in OUTPUT_FILE.glob("TX_100*.pdf"):
    old_pdf.unlink()

records = []
for query in query_data:
    transaction_id = f"TX_100{idx}"
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

    if final_data["source_doc"] == "":
        final_data["state"] = "ACTION_REQUIRED"
    elif final_data["transaction_value"] > final_data["allowed_ceiling"] : 
        final_data["state"] = "NON_COMPLIANT"
    else:
        final_data["COMPLIANT"] = "COMPLIANT"


    records.append(final_data)
    
with open(SEED_DATA, "w") as file:
    json.dump(records,file,indent=4)
    
    
