"""Сквозная проверка пути e5 на НАСТОЯЩИХ onnxruntime и tokenizers с крошечной моделью (без весов e5).

Граф повторяет выход export_e5.py: input_ids, attention_mask -> Gather -> MatMul -> среднее по маске -> L2
-> "embedding". Так проверяются загрузка файлов, имена входов, типы, паддинг, квантование int8
(export_e5.quantize) и работа Deduper/loader с этой папкой. Экспорт из PyTorch — только у владельца (LOCAL).
"""

import json

import pytest

np = pytest.importorskip("numpy")
onnx = pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")
tokenizers = pytest.importorskip("tokenizers")

from onnx import TensorProto, helper, numpy_helper  # noqa: E402

from ml.civic_dedup import config as C  # noqa: E402
from ml.civic_dedup import get_deduper, loader  # noqa: E402
from ml.civic_dedup.e5 import META_NAME, E5Scorer, E5Unavailable  # noqa: E402
from ml.civic_dedup.export_e5 import quantize  # noqa: E402
from ml.civic_dedup.fixtures import PHRASES  # noqa: E402

from conftest import NOW, STOP, record  # noqa: E402

DIM = 32


def build_model_dir(path, *, output="embedding"):
    words = sorted({w for ts in PHRASES.values() for t in ts for w in t.lower().replace(",", " ").split()})
    vocab = {"<s>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3, "query:": 4}
    for w in words:
        vocab.setdefault(w, len(vocab))
    tok = tokenizers.Tokenizer(tokenizers.models.WordLevel(vocab, unk_token="<unk>"))
    tok.normalizer = tokenizers.normalizers.Lowercase()
    tok.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    tok.save(str(path / "tokenizer.json"))

    rng = np.random.default_rng(7)
    emb = rng.normal(size=(len(vocab), DIM)).astype(np.float32)
    proj = (np.eye(DIM) + 0.1 * rng.normal(size=(DIM, DIM))).astype(np.float32)
    nodes = [
        helper.make_node("Gather", ["emb", "input_ids"], ["tok"]),
        helper.make_node("MatMul", ["tok", "proj"], ["hidden"]),
    ]
    if output == "embedding":
        nodes += [
            helper.make_node("Cast", ["attention_mask"], ["maskf"], to=TensorProto.FLOAT),
            helper.make_node("Unsqueeze", ["maskf", "axis_last"], ["mask3"]),
            helper.make_node("Mul", ["hidden", "mask3"], ["masked"]),
            helper.make_node("ReduceSum", ["masked", "axis1"], ["summed"], keepdims=0),
            helper.make_node("ReduceSum", ["mask3", "axis1"], ["count"], keepdims=0),
            helper.make_node("Max", ["count", "eps"], ["count_safe"]),
            helper.make_node("Div", ["summed", "count_safe"], ["pooled"]),
            helper.make_node("LpNormalization", ["pooled"], ["embedding"], axis=-1, p=2),
        ]
        out = helper.make_tensor_value_info("embedding", TensorProto.FLOAT, ["batch", DIM])
    else:
        nodes += [helper.make_node("Identity", ["hidden"], ["last_hidden_state"])]
        out = helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, ["batch", "seq", DIM])
    inits = [numpy_helper.from_array(emb, "emb"), numpy_helper.from_array(proj, "proj"),
             numpy_helper.from_array(np.array([-1], dtype=np.int64), "axis_last"),
             numpy_helper.from_array(np.array([1], dtype=np.int64), "axis1"),
             numpy_helper.from_array(np.array([1e-9], dtype=np.float32), "eps")]
    graph = helper.make_graph(
        nodes, "tiny_e5",
        [helper.make_tensor_value_info("input_ids", TensorProto.INT64, ["batch", "seq"]),
         helper.make_tensor_value_info("attention_mask", TensorProto.INT64, ["batch", "seq"])],
        [out], initializer=inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path / "model.onnx"))
    (path / META_NAME).write_text(json.dumps({"model_id": "tiny/test-e5", "revision": "0000000", "pad_id": 1,
                                              "max_length": 16, "dim": DIM, "prefix": "query: "}), encoding="utf-8")
    return path


@pytest.mark.parametrize("output", ["embedding", "last_hidden_state"])
def test_load_and_embed_real_runtime(tmp_path, output):
    d = build_model_dir(tmp_path, output=output)
    sc = E5Scorer.load(d)
    assert sc.meta["file"] == "model.onnx" and sc.output == output
    vec = sc.embed(["снег на остановке", "мусорные баки переполнены, не вывозят неделю", ""])
    assert vec.shape == (3, DIM)
    assert np.allclose(np.linalg.norm(vec, axis=1), 1.0, atol=1e-5)
    # паддинг не влияет на эмбеддинг: тот же текст в одиночку и в пакете с длинным соседом
    alone = sc.embed(["снег на остановке"])[0]
    assert np.allclose(alone, vec[0], atol=1e-5)


def test_truncation_by_max_length(tmp_path):
    sc = E5Scorer.load(build_model_dir(tmp_path))
    long = " ".join(["снег"] * 500)
    assert sc.embed([long]).shape == (1, DIM)
    enc = sc.tokenizer.encode_batch(["query: " + long])[0]
    assert len(enc.ids) == 16


def test_quantize_int8_close_to_fp32(tmp_path):
    d = build_model_dir(tmp_path)
    info = quantize(d / "model.onnx", d / "model.int8.onnx")
    assert (d / "model.int8.onnx").exists() and info["weight_type"] == "QInt8"
    assert not (d / "model.clean.onnx").exists() and not (d / "model.pre.onnx").exists()
    texts = [t for ts in PHRASES.values() for t in ts]
    fp32 = E5Scorer.load(d, onnx_name="model.onnx").embed(texts)
    int8 = E5Scorer.load(d).embed(texts)            # по умолчанию берётся int8
    assert E5Scorer.load(d).meta["file"] == "model.int8.onnx"
    cos = (fp32 * int8).sum(axis=1)
    assert cos.min() > 0.98


def test_corrupted_onnx_is_unavailable_not_crash(tmp_path):
    d = build_model_dir(tmp_path)
    (d / "model.int8.onnx").write_bytes(b"\x00broken")
    with pytest.raises(E5Unavailable):
        E5Scorer.load(d)


def test_loader_and_deduper_use_real_e5_dir(tmp_path, monkeypatch):
    d = build_model_dir(tmp_path)
    conf = json.loads(json.dumps(C.DEFAULTS))
    conf["methods"]["e5-onnx"]["threshold"] = 0.9
    monkeypatch.setattr(C, "load_config", lambda path=None: conf)
    monkeypatch.setattr(C, "E5_DIR", d)
    loader.reset()
    dd = get_deduper()
    assert dd.scorer.method == "e5-onnx" and dd.threshold == 0.9
    recs = [record("c-rt000001", "не убран снег на остановке"), record("c-rt000002", "мусорные баки переполнены")]
    ids = [m.complaint_id for m in dd.find("не убран снег на остановке", recs, point=STOP, now=NOW)]
    assert ids == ["c-rt000001"]
    loader.reset()
