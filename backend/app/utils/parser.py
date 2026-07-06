import pdfplumber
import json
import re
from collections import Counter
from pathlib import Path

def save_file(new_path,data):
        new_path = Path(new_path)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving the new text file, at: {new_path} \n")

        with new_path.open("w") as file:
            json.dump(data,file,indent=4, sort_keys=True)


def detect_page_regions(pdf :pdfplumber.PDF)->list[dict]:
    page_lines = []
    header_counts = Counter()
    footer_counts = Counter()

    def group_words_into_lines(words, tolerance=3):
        lines = []
        for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
            if not lines or abs(word["top"] - lines[-1][0]["top"]) > tolerance:
                lines.append([word])
            else:
                lines[-1].append(word)

        grouped_lines = []
        for words_in_line in lines:
            words_in_line.sort(key=lambda item: item["x0"])
            grouped_lines.append({
                "text": " ".join(word["text"] for word in words_in_line).strip(),
                "top": min(word["top"] for word in words_in_line),
                "bottom": max(word["bottom"] for word in words_in_line),
            })
        return grouped_lines

    def normalize_edge_line(text):
        normalized = " ".join(text.lower().split())
        compact = re.sub(r"\s+", "", normalized)
        if "website:www.fema.rbi.org.in" in compact and "email:fedcofid@rbi.org.in" in compact:
            return "<rbi-contact-footer>"
        normalized = re.sub(r"https?://\S+", "<url>", normalized)
        return re.sub(r"\b\d+\b", "#", normalized)

    def preserve_line(text):
        return bool(re.match(
            r"^(item|part|chapter|section|annex|annexure|amended|inserted|deleted)\b",
            text.strip(),
            flags=re.IGNORECASE,
        ) or re.search(r"\b(circular|with effect from)\b", text, re.IGNORECASE))

    for page in pdf.pages:
        _, page_top, _, page_bottom = page.bbox
        edge_size = (page_bottom - page_top) * 0.10
        header_limit = page_top + edge_size
        footer_limit = page_bottom - edge_size
        candidates = {"header": [], "footer": []}

        for line in group_words_into_lines(page.extract_words()):
            if not line["text"] or preserve_line(line["text"]):
                continue

            if line["bottom"] <= header_limit:
                line["signature"] = normalize_edge_line(line["text"])
                candidates["header"].append(line)
            elif line["top"] >= footer_limit:
                line["signature"] = normalize_edge_line(line["text"])
                candidates["footer"].append(line)

        header_counts.update({line["signature"] for line in candidates["header"]})
        footer_counts.update({line["signature"] for line in candidates["footer"]})
        page_lines.append(candidates)

    minimum_repetitions = max(3, round(len(pdf.pages) * 0.20))
    repeated_headers = {
        signature for signature, count in header_counts.items()
        if count >= minimum_repetitions
    }
    repeated_footers = {
        signature for signature, count in footer_counts.items()
        if count >= minimum_repetitions
    }

    regions = []
    for page_number, (page, candidates) in enumerate(
        zip(pdf.pages, page_lines), start=1
    ):
        x0, top, x1, bottom = page.bbox
        removed_headers = [
            line for line in candidates["header"]
            if line["signature"] in repeated_headers
        ]
        removed_footers = [
            line for line in candidates["footer"]
            if line["signature"] in repeated_footers
        ]

        if removed_headers:
            top = max(line["bottom"] for line in removed_headers) + 2
        if removed_footers:
            bottom = min(line["top"] for line in removed_footers) - 2

        if top >= bottom or bottom - top < page.height * 0.70:
            top, bottom = page.bbox[1], page.bbox[3]

        regions.append({
            "page": page_number,
            "bbox": (x0, top, x1, bottom),
            "headers_removed": [line["text"] for line in removed_headers],
            "footers_removed": [line["text"] for line in removed_footers],
        })

    return regions

def identify_heading(line : str):
    line = line.strip()
    if not line or len(line) >= 120 or "..." in line:
        return False

    named_heading = re.fullmatch(
        r"(?:"
        r"item\s+\d+[a-z]?(?:\s*[.\-:]\s*[^.]+)?|"
        r"(?:part|chapter|section)\s*(?:[-:]\s*)?[ivxlcdm\d]+"
        r"(?:\s+(?:and|&)\s+[ivxlcdm\d]+)?(?:\s*[.\-:]\s*[^.]+)?|"
        r"annex(?:ure)?\s*(?:[-:]\s*)?[a-z\d]+(?:\s*[.\-:]\s*[^.]+)?"
        r")",
        line.rstrip("."),
        flags=re.IGNORECASE,
    )
    numbered_heading = re.match(
        r"^(?:\d+(?:\.\d+)+|\d+[.)])\s+(.+)$",
        line,
    )
    if numbered_heading:
        heading_text = numbered_heading.group(1)
        words = re.findall(r"[A-Za-z]+", heading_text)
        minor_words = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
        significant_words = [word for word in words if word.lower() not in minor_words]
        capitalized_words = [word for word in significant_words if word[0].isupper()]
        looks_like_title = (
            bool(significant_words)
            and len(words) <= 10
            and len(capitalized_words) == len(significant_words)
        )
    else:
        looks_like_title = False

    return bool(named_heading or looks_like_title)


def clean_table_rows(table):
    return [
        [cell.strip() if isinstance(cell, str) else "" for cell in row]
        for row in table.extract()
    ]


def is_valid_table(rows):
    column_count = max((len(row) for row in rows), default=0)
    nonempty_cells = sum(bool(cell) for row in rows for cell in row)
    return len(rows) >= 2 and column_count >= 2 and nonempty_cells >= 4


class Parser:
    def __init__(self,file_path:str):
        source_path = Path(file_path)
        self.file_path = str(source_path)

        if source_path.parent.name == "raw":
            output_directory = source_path.parent.parent / "processed"
        else:
            output_directory = source_path.parent

        self.new_path = str(
            output_directory / source_path.with_suffix(".json").name
        )
        self.data = []


    def processing(self):
        with pdfplumber.open(self.file_path) as pdf:
            
            regions = detect_page_regions(pdf)
            json_data = []
            record_fingerprints = set()
            current_section = None
            table_index = 1

            def append_unique(record):
                fingerprint = (
                    record["page_number"],
                    record["content_type"],
                    record["section_inferred"],
                    json.dumps(record["raw_content"], sort_keys=True),
                )
                if fingerprint not in record_fingerprints:
                    record_fingerprints.add(fingerprint)
                    json_data.append(record)

            for page, region in zip(pdf.pages, regions):
                
                #Removing header and footer pixels
                body = page.crop(region["bbox"])
                
                #Extracting tables
                detected_tables = body.find_tables()
                tables = []
                for table in detected_tables:
                    cleaned_rows = clean_table_rows(table)
                    if is_valid_table(cleaned_rows):
                        tables.append((table, cleaned_rows))

                table_bboxes = [table.bbox for table, _ in tables]

                #Extracting text body without tables
                text_body = body.filter(
                    lambda obj: not any(
                        x0 <= (obj["x0"] + obj["x1"]) / 2 <= x1
                        and top <= (obj["top"] + obj["bottom"]) / 2 <= bottom
                        for x0, top, x1, bottom in table_bboxes
                    )
                )
                text = text_body.extract_text() or ""
                raw_content = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    if identify_heading(line):
                        if raw_content:
                            append_unique({
                                "source_document": Path(self.file_path).name,
                                "page_number": region["page"],
                                "section_inferred": current_section,
                                "content_type": "text",
                                "raw_content": "\n".join(raw_content).strip()
                            })
                        current_section = line
                        raw_content = [line]
                        continue
                    raw_content.append(line)

                if raw_content:
                    append_unique({
                        "source_document": Path(self.file_path).name,
                        "page_number": region["page"],
                        "section_inferred": current_section,
                        "content_type": "text",
                        "raw_content": "\n".join(raw_content).strip()
                    })

                for table, cleaned_rows in tables:
                    append_unique({
                        "source_document": Path(self.file_path).name,
                        "page_number": region["page"],
                        "section_inferred": current_section,
                        "content_type": "table",
                        "table_index":table_index,
                        "raw_content": cleaned_rows
                    })
                    table_index += 1

            self.data.extend(json_data)

                
if __name__ == "__main__":
    pdf_list = [
        "data/raw/apple-SEC.pdf",
        "data/raw/credit_Risk_RBI.pdf",
        "data/raw/foreign_Investement_rbi.pdf",
        "data/raw/kyc_rbi.pdf",
        "data/raw/microsoft-SEC.pdf",
        "data/raw/nexus_holdings_global_inc.pdf"
    ]

    for file in pdf_list:
        par = Parser(file)
        par.processing()
        save_file(par.new_path,par.data)
    
    print("\nProcessing and Storing complete!\n")

    
