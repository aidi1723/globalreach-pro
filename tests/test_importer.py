from app.services import importer


def test_auto_map_fields_prefers_known_headers():
    headers = ["Contact Email", "Buyer Company", "Full Name", "Main Product"]
    rows = [
        {
            "Contact Email": "alice@example.com",
            "Buyer Company": "Acme Trading Ltd",
            "Full Name": "Alice Chen",
            "Main Product": "aluminum windows",
        }
    ]

    mapping, details = importer.auto_map_fields(headers, rows)

    assert mapping == {
        "email": "Contact Email",
        "company": "Buyer Company",
        "name": "Full Name",
        "product": "Main Product",
    }
    assert details["email"]["confidence"] in {"medium", "high"}


def test_load_leads_csv_encoding_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "pd", None)
    csv_path = tmp_path / "gb.csv"
    csv_path.write_text(
        "邮箱,公司,姓名,产品\nsales@example.com,深圳科技有限公司,张三,铝窗\n",
        encoding="gb18030",
    )

    dataset = importer.load_leads(str(csv_path))

    assert dataset.total_rows == 1
    assert dataset.rows[0]["公司"] == "深圳科技有限公司"
    assert dataset.field_mapping["email"] == "邮箱"


def test_load_leads_strips_dirty_rows_and_empty_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "pd", None)
    csv_path = tmp_path / "dirty.csv"
    csv_path.write_text(
        "Email,Company,Name,Product\n"
        "\n"
        " buyer@example.com , Acme Ltd , Alice , Window \n"
        ",,,\n",
        encoding="utf-8",
    )

    dataset = importer.load_leads(str(csv_path))

    assert dataset.total_rows == 1
    assert dataset.rows[0] == {
        "Email": "buyer@example.com",
        "Company": "Acme Ltd",
        "Name": "Alice",
        "Product": "Window",
    }


def test_load_leads_skips_title_row_before_real_header(tmp_path):
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(
        '"智枢获客系统 - 全部结果"\n'
        "\n"
        "name,phone,website,address,email,category,sunday\n"
        '"Almes Doors","(917) 920-5435","https://almesdoors.com/","Brooklyn","sales@almesdoors.com","门业制造商",""\n',
        encoding="utf-8",
    )

    dataset = importer.load_leads(str(csv_path))

    assert dataset.headers == ["name", "phone", "website", "address", "email", "category", "sunday"]
    assert dataset.total_rows == 1
    assert dataset.rows[0]["email"] == "sales@almesdoors.com"
    assert dataset.field_mapping["email"] == "email"


def test_auto_map_fields_detects_email_inside_noisy_contact_values():
    headers = ["Contact Info", "Organization", "Buyer"]
    rows = [
        {
            "Contact Info": "Alice Chen <alice@example.com>",
            "Organization": "Acme Trading Ltd",
            "Buyer": "Alice Chen",
        },
        {
            "Contact Info": "mailto:bob@example.com",
            "Organization": "Beta Industrial Co",
            "Buyer": "Bob Li",
        },
    ]

    mapping, details = importer.auto_map_fields(headers, rows)

    assert mapping["email"] == "Contact Info"
    assert details["email"]["confidence"] in {"medium", "high"}
    assert importer.extract_email_address("Sales Team <sales@example.com>") == "sales@example.com"


def test_auto_map_fields_does_not_treat_social_links_as_company():
    headers = ["Name", "Email", "LinkedIn", "Website"]
    rows = [
        {
            "Name": "Alice Chen",
            "Email": "alice@example.com",
            "LinkedIn": "https://www.linkedin.com/company/example-co",
            "Website": "https://example.com",
        }
    ]

    mapping, _details = importer.auto_map_fields(headers, rows)

    assert mapping["company"] is None
