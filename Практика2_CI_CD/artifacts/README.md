# Артефакты конвейера практики 2

Здесь лежат файлы, которые на самом деле выдали четыре джобы из
`.gitlab-ci.yml`. В GitLab то же самое показывается кнопкой **Artifacts** у каждой
джобы и вкладкой **Tests** у пайплайна; сервер поднимать не обязательно, чтобы
увидеть содержимое, — все джобы прогоняются в тех же образах локально:

```bash
bash Практика2_CI_CD/scripts/run_jobs_locally.sh
```

Прогон занимает пару минут и перезаписывает всё в этой папке.

## Что где лежит

| Путь | Какая джоба | Что это |
|---|---|---|
| `build_app/job.log` | `build_app`, образ `dotnet/sdk:8.0` | вывод `dotnet restore` и `dotnet publish`, в конце `[exit code] 0` |
| `build_app/publish/` | `build_app` | тот самый артефакт стадии сборки: `FileManagerApp.dll`, `.deps.json`, `.runtimeconfig.json`, `.pdb`, launcher |
| `build_app/publish.listing.txt` | `build_app` | список файлов артефакта и его размер |
| `run_tests/job.log` | `run_tests`, образ `dotnet/sdk:8.0` | 18 строк `OK: ...` из `--selfcheck`, который идёт уже по собранному `publish/` |
| `run_tests/test-results.xml` | `run_tests` | JUnit-отчёт: `tests="18" failures="0" errors="0"` — в GitLab он уходит во вкладку Tests через `artifacts.reports.junit` |
| `security_scan/job.log` | `security_scan`, образ `semgrep/semgrep` | `Ran 52 rules on 11 files: 0 findings.` Код 0 — значит конвейер не прерван |
| `security_scan/semgrep_app.json` | `security_scan` | тот же скан без `--severity ERROR`: машинночитаемый список пройденных файлов и находок по рабочему приложению |
| `security_scan/demo_job.log` | `security_scan`, мишень `sast_demo/` | доказательство, что gate работает: 1 находка уровня ERROR, код возврата 1, конвейер остановлен |
| `security_scan/demo_findings.json` | то же | находка в JSON: `csharp.lang.security.sqli`, CWE-89, строка 33 |
| `security_scan/demo_all_levels.json` | то же, без `--severity` | три находки вместо одной: CWE-89 (ERROR), CWE-22 и CWE-502 (WARNING) |
| `local_deploy/job.log` | `local_deploy`, образ `docker:24.0` | сборка финального образа и `docker run --rm filemanagerapp:local --selfcheck` внутри него |
| `local_deploy/image.inspect.txt` | `local_deploy` | `docker image inspect`: id, размер, `User=appuser`, entrypoint |
| `local_deploy/image.layers.txt` | `local_deploy` | `docker history` — видно, что SDK-слоёв в финальном образе нет |

## Почему у стадии SAST два прогона, а не один

Один прогон по чистому проекту даёт `0 findings` — по этому нельзя сказать,
работает ли блокировка вообще. Поэтому рядом лежит прогон по `sast_demo/` —
заведомо уязвимому файлу, который в сборку не входит. Он обязан вернуть
ненулевой код, и скрипт это проверяет двумя условиями сразу: ненулевой код
возврата И непустой список находок. Одно только «упало» ничего не доказывает —
Semgrep возвращает код 2 и на собственных ошибках запуска.

Из семи подложенных в мишень проблем Semgrep нашёл три, блокирует одну.
Оставшиеся четыре (MD5, вызов `cmd.exe`, секрет в константе, `Random` для
токена) разбираются руками — для этого рядом лежит `review_CWE.md`.

## Порядок, в котором это показывать

1. Открыть `.gitlab-ci.yml` и найти в каждой джобе блок `artifacts:` — вот он и объясняет, что должно появиться.
2. `build_app/publish/` — артефакт стадии сборки. Отдельно отметить, что собран он внутри контейнера,
   а не на хосте.
3. `run_tests/test-results.xml` — открыть и показать строку с `tests="18" failures="0" errors="0"`.
   Это ровно те 18 проверок, что перечислены в `run_tests/job.log`.
4. `security_scan/job.log` — 0 находок при `--severity ERROR`, поэтому джоба не упала и конвейер пошёл дальше.
5. `security_scan/demo_job.log` — тут наоборот: по мишени `sast_demo/` джоба падает
   с кодом 1 на CWE-89. Это и есть доказательство, что блокировка настоящая.
   Рядом `demo_all_levels.json` — те же данные без фильтра по уровню, там три находки.
6. `../review_CWE.md` — ручной обзор: семь приёмов из мишени, CWE, что сказал сканер
   и чем каждый закрыт в рабочем приложении.
7. `local_deploy/image.inspect.txt` — `User=appuser`, то есть приложение в образе не от root;
   в `image.layers.txt` видно, что это уже runtime-образ без SDK.

## Одна правка, которая появилась именно из-за этого прогона

Первый честный прогон стадии `test` в контейнере упал: в образе `dotnet/sdk:8.0`
нет пакета `libsqlite3`, а `FileManagerApp` обращается к SQLite через P/Invoke,
минуя NuGet-пакет. Локально на Windows этого не видно, потому что `winsqlite3.dll`
есть в системе, а в Linux-контейнере тестам нужна именно `libsqlite3.so.0`.

Поэтому в `run_tests` добавлена установка пакета перед запуском — та же
`libsqlite3-0`, что стоит в `Dockerfile` для финального образа. После этого
`tests="18" failures="0" errors="0"`, код 0.
