"""模板接口基础测试。"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    """健康检查应返回正常状态。"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_predict() -> None:
    """模板预测接口应返回示例结果。"""
    payload = {
        "task_id": "test-task",
        "params": {
            "sample_id": "demo",
            "threshold": 0.5,
            "top_k": 5,
        },
        "input_files": None,
    }

    response = client.post("/predict", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["task_id"] == "test-task"
    assert body["result"]["summary"] == "Template prediction for demo"
