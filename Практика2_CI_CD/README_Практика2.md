# Практика 2. Локальный CI/CD для FileManagerApp

Колесников А.Ю., БСБО-03-23, студ. билет 23Б0099

## Что тут лежит

Готовый отчёт: `Отчет_Практика2.docx` и `Отчет_Практика2.pdf`.

- `Dockerfile` — многоступенчатая сборка FileManagerApp из Практики 1: сначала
  компиляция в образе с SDK, потом в финальный runtime-образ копируются только
  опубликованные файлы. Приложение запускается от пользователя `appuser`
  (uid 10001), а не от root. В runtime-образ отдельно ставится `libsqlite3-0`,
  потому что SQLite вызывается через P/Invoke.
- `.gitlab-ci.yml` — конвейер из четырёх стадий: `build` → `test` → `sast` →
  `deploy`.
- `scripts/run_selfcheck_as_junit.sh` — запускает `FileManagerApp.dll
  --selfcheck` и превращает строки `OK: ...` в JUnit XML, чтобы GitLab
  показывал проверки во вкладке Tests.
- `.dockerignore` — в образ не попадают локальные `bin/`, `obj/` и файлы БД.

В корне комплекта лежит ещё один `.gitlab-ci.yml` — он только подключает
конфиг из этой папки через `include`, потому что GitLab ищет файл конвейера
строго в корне репозитория. Все пути в `Dockerfile` и `.gitlab-ci.yml`
отсчитаны от корня, поэтому `docker build` запускается так:

```bash
docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .
```

## Почему нет xUnit/NUnit

У FileManagerApp нет сторонних NuGet-пакетов, и тащить тестовый фреймворк
только ради одной джобы не хотелось. Вместо этого в само приложение встроен
режим `--selfcheck`: он на временных файлах проверяет регистрацию и вход,
создание/изменение/удаление файла, права на чужой файл, экспорт и импорт
JSON/XML, создание и распаковку ZIP, защиту от path traversal и записи в
журнале. Всего 18 проверок; если хоть одна не прошла, процесс завершается с
кодом 1 и джоба `run_tests` падает.

Скрипт `run_selfcheck_as_junit.sh` разбирает вывод самопроверки и делает из
каждой строки `OK: ...` отдельный `<testcase>`. В отчёте получается 18
тест-кейсов, как будто использовался обычный `dotnet test`.

## Стадии конвейера

1. **build_app** — `dotnet restore` и `dotnet publish -c Release` в образе
   `mcr.microsoft.com/dotnet/sdk:8.0`. Папка `publish/` сохраняется как
   артефакт.
2. **run_tests** — берёт артефакт из `build`, запускает самопроверку и
   публикует `test-results.xml` в отчётах JUnit.
3. **security_scan** — Semgrep с `--config auto --severity ERROR --error`.
   Находки уровня ERROR роняют конвейер, предупреждения — нет.
4. **local_deploy** — сборка Docker-образа и запуск контейнера с
   `--selfcheck`. Выполняется только для веток `main` и `master`.

## Как я это проверял

Полноценный GitLab-сервер с раннером не поднимал, стадии прогнал локально
теми же командами, что записаны в конфиге. Сначала публикация и JUnit:

```bash
cd Практика1_Файловый_менеджер/FileManagerApp
dotnet publish -c Release -o ../../publish
cd ../..

bash "Практика2_CI_CD/scripts/run_selfcheck_as_junit.sh" \
  publish/FileManagerApp.dll test-results.xml
```

В `test-results.xml` получилось 18 тест-кейсов без ошибок, сам `--selfcheck`
напечатал `SELFCHECK: все проверки пройдены успешно`.

Docker-образ и запуск:

```bash
docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .
docker run --rm filemanagerapp:local --selfcheck
```

Образ собрался, размер около 288 МБ, контейнер отработал самопроверку и
вернул код 0.

Semgrep:

```powershell
docker run --rm -v "${PWD}:/src" -w "/src/Практика1_Файловый_менеджер/FileManagerApp" semgrep/semgrep semgrep scan --config auto --severity ERROR --error --exclude bin --exclude obj .
```

Находок уровня ERROR не было. Тонкость: Semgrep не принимает путь с
кириллицей как корень сканирования и падает с `Invalid scanning root`.
Поэтому и в конфиге, и в команде сначала переходим в папку приложения, а
сканируем текущий каталог `.`, а не полный путь. В `.gitlab-ci.yml` у джобы
`security_scan` стоит `entrypoint: [""]`: у образа `semgrep/semgrep` точкой
входа является сам `semgrep`, и без сброса entrypoint раннер передал бы
`cd ...` как аргументы сканеру.

Если запускать именно GitLab CI, нужен runner. Пример регистрации в
Docker-executor:

```bash
docker run -d --name gitlab-runner --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v gitlab-runner-config:/etc/gitlab-runner \
  gitlab/gitlab-runner:latest

docker exec -it gitlab-runner gitlab-runner register \
  --url https://gitlab.com/ \
  --registration-token <ТОКЕН_ИЗ_НАСТРОЕК_РЕПОЗИТОРИЯ> \
  --executor docker \
  --docker-image mcr.microsoft.com/dotnet/sdk:8.0 \
  --docker-privileged
```

`--docker-privileged` нужен сервису `docker:24.0-dind`: без него сборка
образов внутри контейнера не запустится. На общей машине так делать не
стоит, для домашнего стенда это приемлемо.

## Про секреты и проброс портов

Секретов в конвейере нет: приложение локальное, внешний registry не
используется. Если понадобится приватный registry, логин и пароль не
записываются в YAML, а задаются в настройках репозитория
Settings → CI/CD → Variables с флагами Masked и Protected. В скрипте они
подставляются как `$CI_REGISTRY_USER` и `$CI_REGISTRY_PASSWORD`; локально —
через переменные окружения. В репозитории этих значений нет.

Порт в `local_deploy` не пробрасывается, потому что FileManagerApp —
консольное приложение, HTTP-сервера у него нет. Проверка запуска сделана
через `--selfcheck`: контейнер должен отработать и вернуть код 0. Если бы
приложение было веб-сервисом, здесь было бы что-то вроде
`docker run -d -p 8080:8080 myapp:latest`.

## О рисках локального раннера

- **Проброс `/var/run/docker.sock`** даёт джобе `local_deploy` полный контроль
  над Docker на хосте: через сокет можно запустить контейнер с любыми
  привилегиями. На учебной машине это допустимо, в продакшене так не делают —
  там нужен отдельный изолированный runner.
- **`docker:24.0-dind` в привилегированном режиме** нужен для сборки образов
  внутри контейнера, но при этом контейнер получает больше прав, чем само
  приложение. Для домашней лаборатории это нормально, для общего GitLab —
  лучше отдельный runner с ограниченным доступом.
- **Semgrep с `--error`** останавливает конвейер на находках уровня ERROR, но
  не заменяет ручное ревью: сигнатуры ловят типовые случаи и не знают логики
  приложения.
- **Непривилегированный `appuser`** внутри финального образа снижает ущерб,
  если в приложении найдут уязвимость, но не защищает от ошибок в самом
  Dockerfile и не заменяет обновление базового образа.
- **Секретов в репозитории нет**: токен для регистрации runner'а в пример
  подставляется вручную и в файлы не записывается.

## Защита

**Перед ответом запускаю**

```powershell
cd "Практика1_Файловый_менеджер\FileManagerApp"
dotnet publish -c Release -o ..\..\publish
cd ..\..
bash "Практика2_CI_CD/scripts/run_selfcheck_as_junit.sh" publish/FileManagerApp.dll test-results.xml
docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .
docker run --rm filemanagerapp:local --selfcheck
```

**Порядок показа**

1. Открываю `.gitlab-ci.yml`: четыре стадии `build → test → sast → deploy`, кэш NuGet, артефакт `publish/`, JUnit-отчёт.
2. Показываю `Dockerfile`: multi-stage, финальный образ без SDK, пользователь `appuser` (uid 10001).
3. Показываю `test-results.xml`: `tests="18" failures="0" errors="0"`.
4. Запускаю контейнер и показываю код возврата 0. Если открыт GitLab — вкладка `Build → Pipelines`, затем `Tests`; локально показываю те же команды и логи.
5. Отдельно проговариваю `entrypoint: [""]` у Semgrep: без него `cd` уходит в аргументы сканера.

**Что говорю**

Конвейер повторяет схему из задания. Сборка и тесты идут в контейнере с .NET SDK, поэтому версия .NET на хосте не влияет. `--selfcheck` — это встроенные интеграционные проверки приложения: БД, файлы, JSON/XML, ZIP. Скрипт превращает строки `OK` в JUnit XML, чтобы GitLab показывал 18 тестов во вкладке Tests. Semgrep запускается на стадии SAST и при находке уровня ERROR роняет сборку. Деплой собирает финальный образ и запускает `--selfcheck` уже внутри него. Секреты в YAML не лежат, для приватного registry предусмотрены masked variables.

**Вопросы, к которым готовлюсь**

- Почему не xUnit: отдельный тестовый фреймворк потребовал бы пакеты из NuGet, а здесь проверяются реальные операции приложения; JUnit-формат всё равно соблюдён.
- Почему `docker:24.0-dind` и `--docker-privileged`: для сборки образа внутри раннера; это допустимо только на локальной машине, в продакшене нужен изолированный runner.
- Где кэш: `~/.nuget/packages` через `NUGET_PACKAGES`, ключ `nuget-cache`.
- Что не проверено: полный GitLab-сервер не поднимался, стадии проверены локально теми же командами.
