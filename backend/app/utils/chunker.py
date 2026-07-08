import tiktoken
import json
from pathlib import Path

encoder = tiktoken.get_encoding("cl100k_base")

def normalize_content(raw_content):
    if isinstance(raw_content, list):
        return "\n".join(
            "\t".join(str(cell) for cell in row)
            if isinstance(row, list) else str(row)
            for row in raw_content
        )
    return str(raw_content)

def store_buffer(
        file_path, ongoing_section, 
        ongoing_page,running_buffer, 
        parent_tokens, sec, content_type,
        source_document=None
    ):
    if not running_buffer:
        return sec

    source_stem = Path(file_path).stem
    parent_id = f"parent_{source_stem}_{sec}"
                        
    storing_data = {
        "text_content": running_buffer,
        "metadata": {
            "source_document": source_document or file_path,
            "page_number": ongoing_page,
            "section_inferred": ongoing_section,
            "content_type": content_type
        }
    }
    parent_tokens[parent_id] = storing_data
    return sec + 1

class Chunker:
    def __init__(self, file_path : str):
        global encoder
        self.file_path = file_path
        self.parent_tokens = {}
        self.child_tokens = []

    def parent_chunker(self):
        
        with open(self.file_path, 'r', encoding='utf-8') as file:
            list_json = json.load(file)
            running_buffer = ""
            sec = 1
            ongoing_section = ""
            ongoing_page = 1
            ongoing_source = None


            for section in list_json:
                raw_content = normalize_content(section["raw_content"])

                if raw_content and section["content_type"] == "text":
                    tokens = encoder.encode(raw_content)
                    if (
                        len(encoder.encode(running_buffer)) + len(tokens) <= 512 and
                        ongoing_section == section["section_inferred"] and
                        ongoing_page == section["page_number"]
                    ):
                        running_buffer += "\n" + raw_content if running_buffer else raw_content
                    else:
                        sec = store_buffer(
                            self.file_path, ongoing_section,
                            ongoing_page,running_buffer,
                            self.parent_tokens, sec, "text",
                            ongoing_source
                        )

                        running_buffer = raw_content
                        ongoing_page = section["page_number"]
                        ongoing_section = section["section_inferred"]
                        ongoing_source = section.get("source_document")

                elif raw_content and section["content_type"] == "table":
                        sec = store_buffer(
                            self.file_path, ongoing_section,
                            ongoing_page,running_buffer,
                            self.parent_tokens, sec, "text",
                            ongoing_source
                        )

                        running_buffer = raw_content
                        ongoing_page = section["page_number"]
                        ongoing_section = section["section_inferred"]
                        ongoing_source = section.get("source_document")

                        sec = store_buffer(
                            self.file_path, ongoing_section,
                            ongoing_page,running_buffer,
                            self.parent_tokens, sec, "table",
                            section.get("source_document")
                        )
                        running_buffer = ""

            store_buffer(
                self.file_path, ongoing_section,
                ongoing_page, running_buffer,
                self.parent_tokens, sec, "text",
                ongoing_source
            )

    def child_chunker(self):
        p = 0
        source_stem = Path(self.file_path).stem
        for key,value in self.parent_tokens.items():
            chunk_size = 128 
            overlap = 32
            ch = 0
            p += 1
            if value["metadata"]["content_type"] == "text":
                parent_tokens = encoder.encode(value["text_content"])
                for tok in range(0,len(parent_tokens),(chunk_size-overlap)):
                    ch += 1
                    token_slice = parent_tokens[tok : tok + chunk_size]
                    child_text = encoder.decode(token_slice)
                    child_id = f"child_{source_stem}_{ch}_p{p}"
                    store_data = {
                        "child_id": child_id,
                        "parent_id": key,
                        "text_content": child_text,
                        "metadata": value["metadata"]
                    }

                    self.child_tokens.append(store_data)
                
            else:
                ch += 1
                child_text = value["text_content"]
                child_id = f"child_{source_stem}_{ch}_p{p}"
                store_data = {
                    "child_id":child_id,
                    "parent_id": key,
                    "text_content": child_text,
                    "metadata": value["metadata"]
                }

                self.child_tokens.append(store_data)
        
        output_path = Path("data/processed/child_chunks.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            with output_path.open("r", encoding="utf-8") as file:
                existing_data = json.load(file)
        else:
            existing_data = []
        
        existing_data.extend(self.child_tokens)
        with output_path.open("w", encoding="utf-8") as json_file:
            json.dump(existing_data, json_file, indent=4)  

if __name__ == "__main__":
    pdf_list = [
        "data/processed/apple-SEC.json",
        "data/processed/credit_Risk_RBI.json",
        "data/processed/foreign_Investement_rbi.json",
        "data/processed/kyc_rbi.json",
        "data/processed/microsoft-SEC.json",
        "data/processed/nexus_holdings_global_inc.json"
    ]

    output_path = Path("data/processed/child_chunks.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as json_file:
        json.dump([], json_file, indent=4)

    for file in pdf_list:
        par = Chunker(file)
        par.parent_chunker()
        par.child_chunker()
    
    print("\nChunking and Storing complete!\n")
