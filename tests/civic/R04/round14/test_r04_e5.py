"""E5Scorer без настоящих весов: подставные onnxruntime-сессия и токенизатор (веса — LOCAL-задача).

Проверяется то, что можно проверить в облаке: усреднение по маске, нормировка, выход "embedding",
token_type_ids, смешивание с понятиями, кэш, загрузка без файлов -> E5Unavailable -> запасной путь.
"""

import json

import pytest

np = pytest.importorskip("numpy")

from ml.civic_dedup import config as C  # noqa: E402
from ml.civic_dedup import get_deduper, loader  # noqa: E402
from ml.civic_dedup.e5 import E5Scorer, E5Unavailable, mean_pool  # noqa: E402
from ml.civic_dedup.search import Deduper  # noqa: E402

from conftest import NOW, STOP, record  # noqa: E402


class Enc:
    def __init__(self, ids):
        self.ids = ids


class FakeTokenizer:
    """Слово -> id по хэшу; учитывает префикс "query: " как обычный токен."""

    def encode_batch(self, texts):
        return [Enc([2 + (sum(map(ord, w)) % 50) for w in t.lower().split()][:16] or [3]) for t in texts]


class IO:
    def __init__(self, name):
        self.name = name


class FakeSession:
    """last_hidden_state: эмбеддинг токена = one-hot по id (dim 64) — тексты с общими словами ближе."""

    def __init__(self, output="last_hidden_state", inputs=("input_ids", "attention_mask")):
        self.output = output
        self.inputs = inputs
        self.feeds = []

    def get_inputs(self):
        return [IO(n) for n in self.inputs]

    def get_outputs(self):
        return [IO(self.output)]

    def run(self, names, feed):
        self.feeds.append(feed)
        ids = feed["input_ids"]
        hidden = np.zeros(ids.shape + (64,), dtype=np.float32)
        for i in range(ids.shape[0]):
            for j in range(ids.shape[1]):
                hidden[i, j, ids[i, j] % 64] = 1.0
        if self.output == "embedding":
            mask = feed["attention_mask"][..., None].astype(np.float32)
            return [(hidden * mask).sum(axis=1) * 3.0]  # не нормирован — E5Scorer нормирует сам
        return [hidden]


def test_mean_pool_ignores_padding():
    hidden = np.array([[[1.0, 0.0], [0.0, 1.0], [9.0, 9.0]]], dtype=np.float32)
    mask = np.array([[1, 1, 0]])
    out = mean_pool(hidden, mask)
    assert np.allclose(out, [[2 ** -0.5, 2 ** -0.5]], atol=1e-6)


@pytest.mark.parametrize("output", ["last_hidden_state", "embedding"])
def test_vectors_are_unit_and_similar_texts_score_higher(output):
    sc = E5Scorer(FakeSession(output), FakeTokenizer(), meta={"model_id": "intfloat/multilingual-e5-base"})
    a, b, c = sc.encode_many(["снег на остановке", "снег у остановки", "мусор во дворе"])
    for f in (a, b, c):
        assert abs(float(np.linalg.norm(f.vector)) - 1.0) < 1e-5
    assert sc.score(a, b) > sc.score(a, c)
    assert 0.0 <= sc.score(a, c) <= 1.0


def test_prefix_padding_and_token_type_ids():
    sess = FakeSession(inputs=("input_ids", "attention_mask", "token_type_ids"))
    sc = E5Scorer(sess, FakeTokenizer(), meta={"pad_id": 1})
    sc.embed(["а", "длинный текст из пяти слов"])
    feed = sess.feeds[-1]
    assert feed["input_ids"].shape == feed["attention_mask"].shape == feed["token_type_ids"].shape
    assert feed["attention_mask"][0].sum() == 2          # "query:" + "а"
    assert (feed["input_ids"][0][2:] == 1).all()          # паддинг pad_id


def test_alpha_mixes_concepts():
    pure = E5Scorer(FakeSession(), FakeTokenizer(), alpha=1.0)
    mixed = E5Scorer(FakeSession(), FakeTokenizer(), alpha=0.5)
    a, b = "На остановке нет навеса", "Аялдамада шатыр жоқ"   # разные слова, одно понятие
    assert mixed.score(*mixed.encode_many([a, b])) > pure.score(*pure.encode_many([a, b]))
    assert "a0.5" in mixed.version and "a0.5" not in pure.version


def test_deduper_with_e5_and_cache():
    sess = FakeSession()
    sc = E5Scorer(sess, FakeTokenizer())
    dd = Deduper(sc, threshold=0.5)
    recs = [record("c-e5000001", "снег на остановке не убран"), record("c-e5000002", "мусор во дворе")]
    m = dd.find("снег на остановке", recs, point=STOP, now=NOW)
    assert [x.complaint_id for x in m] == ["c-e5000001"]
    n_runs = len(sess.feeds)
    dd.find("снег на остановке", recs, point=STOP, now=NOW)
    assert len(sess.feeds) == n_runs + 1  # второй раз считается только запрос, записи — из кэша


def test_load_without_files_raises(tmp_path):
    with pytest.raises(E5Unavailable):
        E5Scorer.load(tmp_path)
    (tmp_path / "e5_meta.json").write_text("{}", encoding="utf-8")
    with pytest.raises(E5Unavailable):
        E5Scorer.load(tmp_path)                      # нет model.onnx
    (tmp_path / "model.int8.onnx").write_bytes(b"not an onnx model")
    with pytest.raises(E5Unavailable):
        E5Scorer.load(tmp_path)                      # нет tokenizer.json
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    with pytest.raises(E5Unavailable):
        E5Scorer.load(tmp_path)                      # повреждённые файлы / нет библиотеки — не падение сервера


def test_loader_prefers_e5_when_tuned_and_present(monkeypatch):
    conf = json.loads(json.dumps(C.DEFAULTS))
    conf["methods"]["e5-onnx"]["threshold"] = 0.8
    monkeypatch.setattr(C, "load_config", lambda path=None: conf)
    fake = E5Scorer(FakeSession(), FakeTokenizer(), meta={"model_id": "intfloat/multilingual-e5-base"})
    monkeypatch.setattr(E5Scorer, "load", classmethod(lambda cls, d, **kw: fake))
    loader.reset()
    dd = get_deduper()
    assert dd.scorer is fake and dd.threshold == 0.8
    loader.reset()
