"""R06 раунд 15, задача 1: «Проекты и идеи» открыты всем; тема идеи — для линейной иллюстрации вместо серой лампочки.

Просмотр без входа — те же публичные маршруты, что у жителя (GET /ideas, GET /proposals): проверяем, что они
отвечают без сессии и не отдают служебного (очередь проверки, причину скрытия, чек-лист до решения).
"""

import pytest

from r06r14_helpers import call, context
from ui.civic_store.demo_r14 import DEMO_IDEAS, seed_r14_demo
from ui.civic_store.ideas import TOPICS, topic_of


@pytest.mark.parametrize("texts, obj, topic", [
    ({"title_ru": "Сквер"}, {"kind": "playground"}, "playground"),          # объект 3D важнее слов
    ({"title_ru": "Беседка и скамейки во дворе"}, None, "benches"),
    ({"title_kk": "Аулада орындықтар"}, None, "benches"),
    ({"title_ru": "Посадить деревья вдоль дорожки"}, None, "greening"),
    ({"title_kk": "Аулаға ағаш отырғызу"}, None, "greening"),
    ({"title_ru": "Спортплощадка у школы"}, None, "sports"),                # не «детская площадка»
    ({"title_ru": "Фонтан во дворе", "description_ru": "Детям жарко"}, None, "square"),  # название важнее описания
    ({"title_ru": "Светофор на перекрёстке"}, None, "other"),               # «свет» в «светофоре» — не освещение
    ({"title_ru": "Тут темно вечером"}, None, "lighting"),
    ({"title_ru": "Павильон на остановке"}, None, "stop"),
    ({"title_ru": "Что-то нужно"}, None, "other"),
])
def test_topic_of(texts, obj, topic):
    assert topic_of(texts, obj) == topic
    assert topic in TOPICS


def test_demo_ideas_have_topics_without_grey_bulb():
    topics = {i["key"]: topic_of(i["texts"], i.get("object")) for i in DEMO_IDEAS}
    assert topics == {"square": "square", "sports": "sports", "gazebo": "benches", "lighting": "lighting",
                      "fountain": "square", "bikes": "stop"}


def test_public_lists_need_no_login_and_hide_staff_data(stack):
    svc, v2 = stack
    seed_r14_demo(svc)
    anonymous = context()   # без cookie: житель или акимат без входа
    ideas = call(v2, "GET", "/ideas", ctx=anonymous)
    assert ideas["status"] == 200
    items = ideas["body"]["data"]["items"]
    assert items and all(i["status"] in ("voting", "checking", "project", "rejected") for i in items)
    assert all("topic" in i and i["topic"] in TOPICS for i in items)
    hidden = [i for i in items if i["status"] in ("voting", "checking")]
    assert all(i["check"] is None for i in hidden)                     # чек-лист — только после решения
    projects = call(v2, "GET", "/proposals", ctx=anonymous)
    assert projects["status"] == 200 and len(projects["body"]["data"]["items"]) == 5
    staff = call(v2, "GET", "/staff/ideas", ctx=anonymous)
    assert staff["status"] == 401                                       # очередь проверки — только сотруднику
