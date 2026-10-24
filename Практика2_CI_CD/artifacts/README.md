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
| `local_deploy/job.log` | `local_deploy`, образ `docker:24.0` | сборка финального образа и `docker run --rm filemanagerapp:local --selfcheck` внутри него |
| `local_deploy/image.inspect.txt` | `local_deploy` | `docker image inspect`: id, размер, `User=appuser`, entrypoint |
| `local_deploy/image.layers.txt` | `local_deploy` | `docker history` — видно, что SDK-слоёв в финальном образе нет |

## Порядок, в котором это показывать

1. Открыть `.gitlab-ci.yml` и найти в каждой джобе блок `artifacts:` — вот он и объясняет, что должно появиться.
2. `build_app/publish/` — артефакт стадии сборки. Отдельно отметить, что собран он внутри контейнера,
   а не на хосте.
3. `run_tests/test-results.xml` — открыть и показать строку с `tests="18" failures="0" errors="0"`.
   Это ровно те 18 проверок, что перечислены в `run_tests/job.log`.
4. `security_scan/job.log` — 0 находок при `--severity ERROR`, поэтому джоба не упала и конвейер пошёл дальше.
5. `local_deploy/image.inspect.txt` — `User=appuser`, то есть приложение в образе не от root;
   в `image.layers.txt` видно, что это уже runtime-образ без SDK.

## Одна правка, которая появилась именно из-за этого прогона

Первый честный прогон стадии `test` в контейнере упал: в образе `dotnet/sdk:8.0`
нет пакета `libsqlite3`, а `FileManagerApp` обращается к SQLite через P/Invoke,
минуя NuGet-пакет. Локально на Windows этого не видно, потому что `winsqlite3.dll`
есть в системе, а в Linux-контейнере тестам нужна именно `libsqlite3.so.0`.

Поэтому в `run_tests` добавлена установка пакета перед запуском — та же
`libsqlite3-0`, что стоит в `Dockerfile` для финального образа. После этого
`tests="18" failures="0" errors="0"`, код 0.
