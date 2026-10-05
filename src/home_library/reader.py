"""Stage 2: one model session over the tiles of one photo (see docs/pipeline.md)."""
from importlib import resources


def _template():
    return resources.files("home_library").joinpath("prompts", "shelf_read.txt").read_text(encoding="utf-8")


def render_prompt(manifest):
    """Fill the prompt template from a tiles.json manifest."""
    layout = manifest["layout"]
    rows, columns = len(layout["rows"]), len(layout["columns"])
    values = {
        "COUNT": str(len(manifest["tiles"])),
        "TILES": str(rows * columns),
        "ROWS": str(rows),
        "COLUMNS": str(columns),
        "FILES": " ".join(tile["file"] for tile in manifest["tiles"]),
        "PHOTO": manifest["photo"],
    }
    prompt = _template()
    for name, value in values.items():
        prompt = prompt.replace(f"<<{name}>>", value)
    return prompt
