# Burp Suite Community в контейнере с виртуальным X-сервером.
# Нужен только для практики 5: Burp - GUI-приложение, но под Xvfb он
# запускается без рабочего стола и принимает запросы через обычный proxy.
FROM eclipse-temurin:21-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       xvfb xauth curl \
       libxext6 libxrender1 libxtst6 libxi6 libx11-6 fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /burp

# Сам jar и настройки монтируются с хоста при запуске, чтобы не тащить
# 100-мегабайтный файл в репозиторий. В README показан запуск через
# --entrypoint sh: так можно поднять Xvfb и передать config/project files.
ENTRYPOINT ["xvfb-run", "-a", "java", "-jar", "/burp/app/burpsuite_community.jar"]
