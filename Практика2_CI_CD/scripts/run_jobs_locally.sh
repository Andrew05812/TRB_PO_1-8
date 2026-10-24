#!/usr/bin/env bash
# Прогон стадий конвейера практики 2 локально, но в тех же образах и теми же
# командами, что объявлены в .gitlab-ci.yml. Нужен для одного: показать
# артефакты конвейера как файлы, когда под рукой нет сервера GitLab с кнопкой
# "Artifacts". Каждый джоб пишет лог и свои артефакты в artifacts/<имя_джоба>/.
#
# Как GitLab:
#   - CI_PROJECT_DIR = корень комплекта (туда же, куда и в раннере, кладётся
#     publish/ и test-results.xml);
#   - артефакты предыдущей стадии доступны следующей (publish/ не пересобираем);
#   - джоб падает, если команда внутри него вернула ненулевой код.
#
# Использование:
#   bash Практика2_CI_CD/scripts/run_jobs_locally.sh            # все четыре
#   bash Практика2_CI_CD/scripts/run_jobs_locally.sh build_app  # одну стадию
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P2_DIR="$(dirname "$SCRIPT_DIR")"
ROOT="$(dirname "$P2_DIR")"
ART="$P2_DIR/artifacts"

SDK_IMAGE="mcr.microsoft.com/dotnet/sdk:8.0"
SEMGREP_IMAGE="semgrep/semgrep"
DOCKER_IMAGE="docker:24.0"

APP_DIR="Практика1_Файловый_менеджер/FileManagerApp"

WANT="${1:-all}"

# Под Git Bash MSYS по дороге превращает "/project" в "C:/Program Files/Git/project",
# и docker отказывается принимать такое как рабочую директорию. Отключаем подмену
# путей и передаём монтирование в виндовом виде (C:/...). Под Linux этого не нужно.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        export MSYS_NO_PATHCONV=1
        MOUNT_ROOT="$(cd "$ROOT" && pwd -W)"
        ;;
    *)
        MOUNT_ROOT="$ROOT"
        ;;
esac

mkdir -p "$ART"

note() { echo; echo "=== $* ==="; }

# $1 - имя джобы, $2 - файл лога; всё остальное - команда в контейнере
run_job() {
    local job="$1"; shift
    local logfile="$ART/$1"; shift
    mkdir -p "$ART"
    note "$job"
    if "$@" 2>&1 | tee "$logfile"; then
        echo "[exit code] 0" | tee -a "$logfile"
        return 0
    else
        local rc=${PIPESTATUS[0]}
        echo "[exit code] $rc" | tee -a "$logfile"
        return "$rc"
    fi
}

rc_total=0

# ---------------------------------------------------------------------------
# build_app: компиляция в контейнере с SDK. Артефакт - publish/
# ---------------------------------------------------------------------------
if [ "$WANT" = "all" ] || [ "$WANT" = "build_app" ]; then
    mkdir -p "$ART/build_app"
    run_job build_app build_app/job.log \
        docker run --rm \
            -v "$MOUNT_ROOT:/project" -w /project \
            -e CI_PROJECT_DIR=/project \
            "$SDK_IMAGE" bash -c '
                export NUGET_PACKAGES="$CI_PROJECT_DIR/.nuget/packages"
                cd "'"$APP_DIR"'"
                dotnet restore
                dotnet publish -c Release -o "$CI_PROJECT_DIR/publish"
            ' || rc_total=1

    if [ -d "$ROOT/publish" ]; then
        rm -rf "$ART/build_app/publish"
        cp -r "$ROOT/publish" "$ART/build_app/publish"
        ls -1 "$ART/build_app/publish" > "$ART/build_app/publish.listing.txt"
        du -sh "$ART/build_app/publish" >> "$ART/build_app/publish.listing.txt"
    fi
fi

# ---------------------------------------------------------------------------
# run_tests: берёт publish/ с прошлой стадии, гоняет --selfcheck, пишет JUnit
# ---------------------------------------------------------------------------
if [ "$WANT" = "all" ] || [ "$WANT" = "run_tests" ]; then
    if [ ! -f "$ROOT/publish/FileManagerApp.dll" ]; then
        echo "нет publish/FileManagerApp.dll - сначала прогони build_app" >&2
        rc_total=1
    else
        mkdir -p "$ART/run_tests"
        run_job run_tests run_tests/job.log \
            docker run --rm \
                -v "$MOUNT_ROOT:/project" -w /project \
                -e CI_PROJECT_DIR=/project \
                "$SDK_IMAGE" bash -c '
                    apt-get update -qq && apt-get install -y -qq --no-install-recommends libsqlite3-0
                    cd publish
                    bash "$CI_PROJECT_DIR/Практика2_CI_CD/scripts/run_selfcheck_as_junit.sh" \
                        FileManagerApp.dll "$CI_PROJECT_DIR/test-results.xml"
                ' || rc_total=1
        [ -f "$ROOT/test-results.xml" ] && cp "$ROOT/test-results.xml" "$ART/run_tests/test-results.xml"
    fi
fi

# ---------------------------------------------------------------------------
# security_scan: Semgrep по исходникам приложения, уровень ERROR роняет джобу.
# Параллельно прогоняю тот же сканер по демонстрационной мишени из sast_demo/ -
# иначе в артефактах видно только "0 findings", и по этому нельзя сказать,
# работает ли gate вообще.
# ---------------------------------------------------------------------------
if [ "$WANT" = "all" ] || [ "$WANT" = "security_scan" ]; then
    mkdir -p "$ART/security_scan"

    run_job security_scan security_scan/job.log \
        docker run --rm \
            -v "$MOUNT_ROOT:/project" -w /project \
            --entrypoint "" \
            "$SEMGREP_IMAGE" bash -c '
                cd "'"$APP_DIR"'"
                semgrep scan --config auto --severity ERROR --error \
                    --exclude bin --exclude obj .
            ' || rc_total=1

    # Тот же скан, но без --severity ERROR: видно и предупреждения, которых в
    # проекте нет, и что сканер вообще проходил по файлам. Для GitLab Security
    # Reporting сюда же добавляется --sarif - но в этом проекте он даёт 2 МБ
    # описаний правил при нуле находок, поэтому в артефактах оставлен только
    # JSON: он переносит то же самое компактно и читается глазами.
    docker run --rm \
        -v "$MOUNT_ROOT:/project" -w /project \
        --entrypoint "" \
        "$SEMGREP_IMAGE" bash -c '
            cd "'"$APP_DIR"'"
            semgrep scan --config auto --json --quiet \
                --exclude bin --exclude obj --output /project/semgrep_app.json .
        ' > /dev/null 2>&1
    [ -f "$ROOT/semgrep_app.json" ] && mv "$ROOT/semgrep_app.json" "$ART/security_scan/semgrep_app.json"
    rm -f "$ROOT/semgrep_app.sarif"

    # Демонстрация gate: заведомо уязвимый файл. Джоба ОБЯЗАНА упасть именно
    # из-за находки. Проверяю это двумя условиями сразу: ненулевой код возврата
    # И непустой список находок в JSON. Без второго условия мимо пройдёт любая
    # ошибка запуска Semgrep - например "Invalid scanning root", которая тоже
    # даёт код 2, но к безопасности отношения не имеет.
    #
    # Внутрь папки мишени заходим cd, а не передаём путь аргументом: у корня
    # комплекта кириллические сегменты, и Semgrep на них отказывается
    # сканировать (то же самое описано в комментарии к security_scan в .gitlab-ci.yml).
    note "security_scan: проверка, что gate ловит уязвимый код (sast_demo)"
    docker run --rm \
        -v "$MOUNT_ROOT:/project" -w /project \
        --entrypoint "" \
        "$SEMGREP_IMAGE" bash -c '
            cd Практика2_CI_CD/sast_demo
            semgrep scan --config auto --severity ERROR --error \
                --json --quiet --output /project/demo.json .
        ' > "$ART/security_scan/demo_job.log" 2>&1
    demo_rc=$?
    [ -f "$ROOT/demo.json" ] && mv "$ROOT/demo.json" "$ART/security_scan/demo_findings.json"

    # Считаем находки grep'ом, а не python'ом: под Git Bash путь вида /c/Users
    # до Windows-интерпретатора не доходит, и проверка молча ломалась.
    demo_hits=$(grep -o '"check_id"' "$ART/security_scan/demo_findings.json" 2>/dev/null | wc -l | tr -d ' ')
    case "$demo_hits" in
        ''|*[!0-9]*) demo_hits=0 ;;
    esac

    if [ "$demo_rc" -ne 0 ] && [ "$demo_hits" -gt 0 ]; then
        echo "OK: стадия SAST остановила конвейер - находок: $demo_hits, код возврата: $demo_rc" \
            | tee -a "$ART/security_scan/demo_job.log"
    else
        echo "ПРОБЛЕМА: gate не отработал как ожидалось (находок: $demo_hits, код: $demo_rc)" \
            | tee -a "$ART/security_scan/demo_job.log"
        rc_total=1
    fi

    # Тот же прогон по мишени, но без --severity ERROR: видно, что ловится на
    # уровне предупреждений и что сканер вообще не увидел. Это аргумент для
    # ручного ревью, а не для gate.
    docker run --rm \
        -v "$MOUNT_ROOT:/project" -w /project \
        --entrypoint "" \
        "$SEMGREP_IMAGE" bash -c '
            cd Практика2_CI_CD/sast_demo
            semgrep scan --config auto --json --quiet --output /project/demo_all.json .
        ' > /dev/null 2>&1
    [ -f "$ROOT/demo_all.json" ] && mv "$ROOT/demo_all.json" "$ART/security_scan/demo_all_levels.json"
fi

# ---------------------------------------------------------------------------
# local_deploy: сборка финального образа и запуск --selfcheck внутри него.
# Берём хостовый docker-сокет, чтобы не поднимать dind ради локального показа.
# ---------------------------------------------------------------------------
if [ "$WANT" = "all" ] || [ "$WANT" = "local_deploy" ]; then
    mkdir -p "$ART/local_deploy"
    run_job local_deploy local_deploy/job.log \
        docker run --rm \
            -v "$MOUNT_ROOT:/project" -w /project \
            -v //var/run/docker.sock:/var/run/docker.sock \
            -e CI_PROJECT_DIR=/project \
            "$DOCKER_IMAGE" sh -c '
                docker build -t filemanagerapp:local -f Практика2_CI_CD/Dockerfile .
                docker run --rm filemanagerapp:local --selfcheck
            ' || rc_total=1

    docker image inspect filemanagerapp:local \
        --format 'Id={{.Id}}
Size={{.Size}}
User={{.Config.User}}
Entrypoint={{.Config.Entrypoint}}
Env={{.Config.Env}}' > "$ART/local_deploy/image.inspect.txt" 2>&1
    docker history --no-trunc --format '{{.CreatedBy}}' filemanagerapp:local \
        | head -20 > "$ART/local_deploy/image.layers.txt" 2>&1
fi

note "итог"
echo "артефакты разложены по папкам:"
find "$ART" -maxdepth 1 -mindepth 1 -type d -print | while read -r d; do
    printf '  %-52s %s файлов\n' "$(basename "$d")" "$(find "$d" -type f | wc -l)"
done
exit "$rc_total"
