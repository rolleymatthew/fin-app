"""ResultVO 新契约：success/code/message/data/timestamp/path/durationMs/errorType。"""
import time
from app.models.result import ResultVO


def test_ok_has_success_true_and_message_ok():
    vo = ResultVO.ok({"a": 1}, path="/api/x", durationMs=5)
    assert vo.success is True
    assert vo.code == 0
    assert vo.message == "ok"
    assert vo.data == {"a": 1}
    assert vo.path == "/api/x"
    assert vo.durationMs == 5
    assert vo.errorType is None
    assert isinstance(vo.timestamp, int)
    assert abs(vo.timestamp - int(time.time() * 1000)) < 5000


def test_fail_has_success_false_and_error_type():
    vo = ResultVO.fail(1001, "ETF 不存在", errorType="business", path="/api/etf/get", durationMs=12)
    assert vo.success is False
    assert vo.code == 1001
    assert vo.message == "ETF 不存在"
    assert vo.data is None
    assert vo.path == "/api/etf/get"
    assert vo.durationMs == 12
    assert vo.errorType == "business"


def test_ok_default_data_is_none():
    vo = ResultVO.ok()
    assert vo.data is None
    assert vo.success is True


def test_model_dump_contains_all_eight_fields():
    vo = ResultVO.ok({"k": "v"})
    d = vo.model_dump()
    expected = {"success", "code", "message", "data", "timestamp", "path", "durationMs", "errorType"}
    assert set(d.keys()) == expected