from app.services import license_service


def test_generate_license_is_deterministic():
    assert license_service.generate_license("CYFVK1G3PP") == "2DF776121984FBB1"


def test_verify_license_normalizes_input():
    assert license_service.verify_license(" 2df776121984fbb1 ", "CYFVK1G3PP") is True
    assert license_service.verify_license("BADKEY", "CYFVK1G3PP") is False


def test_legacy_local_license_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GLOBALREACH_ENABLE_LEGACY_LOCAL_LICENSE", raising=False)

    assert license_service.legacy_local_license_enabled() is False


def test_legacy_local_license_can_be_enabled_with_env(monkeypatch):
    monkeypatch.setenv("GLOBALREACH_ENABLE_LEGACY_LOCAL_LICENSE", "1")

    assert license_service.legacy_local_license_enabled() is True


def test_extract_darwin_serial_parses_ioreg_output():
    output = '\n'.join(
        [
            "    | |   \"IOPlatformUUID\" = \"ABC\"",
            '    | |   "IOPlatformSerialNumber" = "CYFVK1G3PP"',
        ]
    )
    assert license_service._extract_darwin_serial(output) == "CYFVK1G3PP"


def test_extract_windows_uuid_parses_wmic_output():
    output = "UUID\nABC-123-XYZ\n\n"
    assert license_service._extract_windows_uuid(output) == "ABC-123-XYZ"


def test_get_machine_id_uses_darwin_serial(monkeypatch):
    monkeypatch.setattr(license_service.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        license_service.subprocess,
        "check_output",
        lambda *_args, **_kwargs: '    | |   "IOPlatformSerialNumber" = "CYFVK1G3PP"\n',
    )

    assert license_service.get_machine_id() == "CYFVK1G3PP"


def test_inspect_license_reports_reason():
    snapshot = license_service.inspect_license("bad", machine_id="CYFVK1G3PP")

    assert snapshot["machine_id"] == "CYFVK1G3PP"
    assert snapshot["expected_key"] == "2DF776121984FBB1"
    assert snapshot["provided_key"] == "BAD"
    assert snapshot["valid"] is False
    assert snapshot["reason"] == "mismatch"
