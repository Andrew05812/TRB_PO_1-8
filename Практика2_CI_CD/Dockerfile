# Многоступенчатая сборка (multi-stage build) - в финальном образе
# не должно остаться SDK, исходников, промежуточных .obj и т.п.,
# только то, что нужно для запуска.

# ---------- этап 1: сборка ----------
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Копируем исходники файлового менеджера. Путь указан от корня контекста
# сборки (а не от места, где лежит сам Dockerfile) - контекст запускается
# из корня репозитория: "docker build -f Практика2_CI_CD/Dockerfile ."
COPY Практика1_Файловый_менеджер/FileManagerApp/ ./FileManagerApp/
WORKDIR /src/FileManagerApp

# dotnet restore оставлен специально, хотя внешних NuGet-пакетов у проекта
# нет (см. комментарий в .csproj) - без него в проекте со сторонними
# библиотеками publish ниже просто не соберётся
RUN dotnet restore

RUN dotnet publish -c Release -o /app/publish --no-restore

# ---------- этап 2: финальный образ для запуска ----------
FROM mcr.microsoft.com/dotnet/runtime:8.0 AS final
WORKDIR /app

# libsqlite3 нужна в рантайме - FileManagerApp дёргает её напрямую через
# P/Invoke (без NuGet-пакета Microsoft.Data.Sqlite, см. SqliteNative.cs)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Запуск приложения от непривилегированного пользователя внутри контейнера -
# отдельное требование задания из методички
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY --from=build /app/publish .
RUN chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["dotnet", "FileManagerApp.dll"]
