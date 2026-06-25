import io
import zipfile

from app.api.v1.retrievals import _normalize_sfdx_download_zip


def test_normalize_sfdx_download_zip_wraps_project_root_and_scaffold():
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sfdx-project.json", "{}")
        zf.writestr("force-app/main/default/classes/Example.cls", "public class Example {}")
        zf.writestr(".sf/internal.json", "{}")

    normalized = _normalize_sfdx_download_zip(source.getvalue(), "retrieval_12345678")

    with zipfile.ZipFile(io.BytesIO(normalized), "r") as zf:
        names = set(zf.namelist())

    assert "retrieval_12345678/sfdx-project.json" in names
    assert "retrieval_12345678/.forceignore" in names
    assert "retrieval_12345678/force-app/main/default/classes/Example.cls" in names
    assert "retrieval_12345678/.sf/internal.json" not in names


def test_normalize_sfdx_download_zip_adds_project_json_when_missing():
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("force-app/main/default/classes/Example.cls", "public class Example {}")

    normalized = _normalize_sfdx_download_zip(source.getvalue(), "retrieval_abcdef12")

    with zipfile.ZipFile(io.BytesIO(normalized), "r") as zf:
        project_json = zf.read("retrieval_abcdef12/sfdx-project.json").decode("utf-8")

    assert '"packageDirectories"' in project_json
    assert '"force-app"' in project_json
