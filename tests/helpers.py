from app.services.importer import LeadDataset


def make_dataset(rows, field_mapping=None, source_path="sample.csv"):
    headers = list(rows[0].keys()) if rows else []
    mapping = {
        "email": "Email",
        "company": "Company",
        "name": "Name",
        "product": "Product",
    }
    if field_mapping:
        mapping.update(field_mapping)
    details = {
        field: {
            "header": mapping.get(field) or "",
            "confidence": "manual" if mapping.get(field) else "none",
            "reason": "test fixture",
        }
        for field in ("email", "company", "name", "product")
    }
    return LeadDataset(
        source_path=source_path,
        headers=headers,
        rows=rows,
        field_mapping=mapping,
        mapping_details=details,
    )
