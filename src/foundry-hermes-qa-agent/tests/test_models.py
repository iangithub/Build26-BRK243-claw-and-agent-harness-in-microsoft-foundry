# ============================================================
# 【檔案說明】models.py 的單元測試
# 驗證 payload contract:三種 input 來源、kind/method 檢查、
# 空 input 的錯誤,以及 message_complete 回覆形狀
# ============================================================

import pytest

from foundry_hermes_qa_agent.errors import InvalidRequestError
from foundry_hermes_qa_agent.models import extract_question, message_complete


def test_input_from_body_input():
    payload = {"kind": "hermes.rpc", "method": "prompt.submit", "input": "問題一"}
    assert extract_question(payload) == "問題一"


def test_input_from_params_input():
    payload = {
        "kind": "hermes.rpc",
        "method": "prompt.submit",
        "params": {"input": "問題二"},
    }
    assert extract_question(payload) == "問題二"


def test_input_from_params_message():
    payload = {
        "kind": "hermes.rpc",
        "method": "prompt.submit",
        "params": {"message": "問題三"},
    }
    assert extract_question(payload) == "問題三"


def test_body_input_takes_priority_over_params():
    payload = {
        "kind": "hermes.rpc",
        "method": "prompt.submit",
        "input": "a",
        "params": {"input": "b", "message": "c"},
    }
    assert extract_question(payload) == "a"


def test_params_input_takes_priority_over_message():
    payload = {
        "kind": "hermes.rpc",
        "method": "prompt.submit",
        "params": {"input": "b", "message": "c"},
    }
    assert extract_question(payload) == "b"


def test_unsupported_kind_raises():
    payload = {"kind": "other.rpc", "method": "prompt.submit", "input": "x"}
    with pytest.raises(InvalidRequestError, match="kind"):
        extract_question(payload)


def test_unsupported_method_raises():
    payload = {"kind": "hermes.rpc", "method": "session.create", "input": "x"}
    with pytest.raises(InvalidRequestError, match="method"):
        extract_question(payload)


def test_missing_kind_field_raises():
    payload = {"method": "prompt.submit", "input": "x"}
    with pytest.raises(InvalidRequestError):
        extract_question(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "hermes.rpc", "method": "prompt.submit"},
        {"kind": "hermes.rpc", "method": "prompt.submit", "input": "   "},
        {"kind": "hermes.rpc", "method": "prompt.submit", "params": {"input": ""}},
        {"kind": "hermes.rpc", "method": "prompt.submit", "params": {"message": "  "}},
    ],
)
def test_empty_input_raises(payload):
    with pytest.raises(InvalidRequestError, match="[Ii]nput"):
        extract_question(payload)


def test_non_dict_body_raises():
    with pytest.raises(InvalidRequestError):
        extract_question(["not", "a", "dict"])


def test_message_complete_shape():
    assert message_complete("回答") == {"type": "message.complete", "text": "回答"}
