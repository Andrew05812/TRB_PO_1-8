#!/usr/bin/env bash
# Запускает FileManagerApp --selfcheck и превращает его вывод в JUnit XML,
# чтобы GitLab CI мог показать результат во вкладке Tests (как и обычный
# отчёт dotnet test --logger trx, только без самого xUnit/NUnit).
#
# Использование: run_selfcheck_as_junit.sh <путь_к_dll> <путь_к_отчёту.xml>

set -uo pipefail

DLL_PATH="${1:?нужно передать путь к FileManagerApp.dll}"
REPORT_PATH="${2:?нужно передать путь, куда писать junit-отчёт}"

OUTPUT=$(dotnet "$DLL_PATH" --selfcheck 2>&1)
EXIT_CODE=$?

# каждая строка "OK: ..." из RunSelfCheck() - это отдельная пройденная проверка,
# превращаем их в отдельные testcase, чтобы в отчёте было видно, что именно проверялось
mapfile -t OK_LINES < <(echo "$OUTPUT" | grep '^  OK: ')
TEST_COUNT=${#OK_LINES[@]}
if [ "$TEST_COUNT" -eq 0 ]; then
    TEST_COUNT=1
fi

esc() {
    # экранируем то, что может сломать xml
    printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

{
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "<testsuite name=\"FileManagerApp.SelfCheck\" tests=\"$TEST_COUNT\" failures=\"0\" errors=\"0\">"
        for line in "${OK_LINES[@]}"; do
            name=$(esc "${line#  OK: }")
            echo "  <testcase classname=\"FileManagerApp.SelfCheck\" name=\"$name\" />"
        done
    else
        echo "<testsuite name=\"FileManagerApp.SelfCheck\" tests=\"1\" failures=\"1\" errors=\"0\">"
        echo "  <testcase classname=\"FileManagerApp.SelfCheck\" name=\"selfcheck\">"
        echo "    <failure message=\"selfcheck завершился с кодом $EXIT_CODE\">$(esc "$OUTPUT")</failure>"
        echo "  </testcase>"
    fi
    echo "</testsuite>"
} > "$REPORT_PATH"

echo "$OUTPUT"
exit "$EXIT_CODE"
