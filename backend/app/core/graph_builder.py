import networkx as nx
import pickle
import json


G = nx.DiGraph()

nodes = [
    "Nexus Holdings",
    "Nexus India",
    "Internal Policy", 
    "RBI KYC",
    "RBI Credit Risk",
    "Foreign Investment",
    "Apple SEC Filings",
    "Microsoft SEC Filings"
]

G.add_nodes_from(nodes)

edges = [
    # Parent company owns the subsidiary
    ("Nexus Holdings", "Nexus India", {"relation": "OWNS_SUBSIDIARY"}),
    
    # Connecting the Parent company to its rule book
    ("Nexus Holdings", "Internal Policy", {"relation": "HAS_POLICY"}),

    # Subsidiary operational boundaries
    ("Nexus India", "RBI KYC", {"relation": "GOVERNED_BY"}),
    ("Nexus India", "RBI Credit Risk", {"relation": "GOVERNED_BY"}),
    ("Nexus India", "Foreign Investment", {"relation": "GOVERNED_BY"}),

    # Market comparisons
    ("Nexus Holdings", "Apple SEC Filings", {"relation": "MARKET_BENCHMARK"}),
    ("Nexus Holdings", "Microsoft SEC Filings", {"relation": "MARKET_BENCHMARK"}),
    
    # Policy cross-reference overlays
    ("Internal Policy", "RBI KYC", {"relation": "COMPLIANCE_OVERLAYS", "remediation_target": "UBO"}),
    ("Internal Policy", "RBI Credit Risk", {"relation": "ALIGN_WITH", "exposure_target": "directors"}),
    ("Internal Policy", "Foreign Investment", {"relation": "CROSS_REFERENCES", "ceiling_usd": 1500000})
]

G.add_edges_from(edges)

with open("data/processed/parent_chunks.json","r") as file:
    parent_json = json.load(file)

#Adding chunks as attributes

G.nodes["Internal Policy"]["chunks"] = [ 
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "nexus_holdings_global_inc.pdf"
]

G.nodes["RBI KYC"]["chunks"] = [
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "kyc_rbi.pdf"
]

G.nodes["RBI Credit Risk"]["chunks"] = [
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "credit_Risk_RBI.pdf"
]

G.nodes["Foreign Investment"]["chunks"] = [
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "foreign_Investement_rbi.pdf"
]

G.nodes["Apple SEC Filings"]["chunks"] = [
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "apple-SEC.pdf"
]

G.nodes["Microsoft SEC Filings"]["chunks"] = [
    doc for doc in parent_json 
    if doc["metadata"]["source_document"] == "microsoft-SEC.pdf"
]

with open("data/processed/knowledge_graph.pkl", "wb") as file:
    pickle.dump(G, file)

print("\nKnowledge Graph topological map successfully initialized and serialized!\n")