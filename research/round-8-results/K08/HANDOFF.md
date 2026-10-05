# HANDOFF — K08 R8

См. STATUS.md. Команды (из корня репозитория, APP = извлечённая prototypes/city-evidence нужного SHA):
```bash
git archive a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d prototypes/city-evidence | tar -x -C /tmp/r8
APP=/tmp/r8/prototypes/city-evidence; K=research/round-8-results/K08
python3 $K/make_fixtures.py --app-root $APP --out $K/fixtures
python3 $K/report.py --app-root $APP build $K/fixtures/shymkent_school_demo.json --out-dir /tmp/rep --generated-utc 2026-10-05T00:00:00Z
python3 $K/test_report.py --app-root $APP -v
```
