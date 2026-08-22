from app.schemas.tasks import TaskCreate, TaskInputSchema


def test_task_create_accepts_standard_input_uploads():
    payload = TaskCreate(
        tool_id="tool-1",
        standard_input_uploads={"protein": "file-1"},
    )

    assert payload.standard_input_uploads == {"protein": "file-1"}


def test_task_input_schema_accepts_standard_input_uploads():
    payload = TaskInputSchema(
        params={},
        standard_input_uploads={"ligand": "file-2"},
    )

    assert payload.standard_input_uploads == {"ligand": "file-2"}
