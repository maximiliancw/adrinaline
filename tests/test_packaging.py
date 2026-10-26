import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_wheel_contains_data_files(tmp_path):
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("adrinaline-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for data in ("template.md", "0001.md", "SKILL.md", "references/frontmatter.md"):
        assert f"adrinaline/data/{data}" in names
