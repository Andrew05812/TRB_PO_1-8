# John the Ripper jumbo для сравнения с собственным переборщиком.
# Готовый образ из Docker Hub оказался старым (2020 год) и не понимает
# формат $argon2id$, поэтому собираем актуальный jumbo из исходников.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git build-essential libssl-dev zlib1g-dev \
        libgmp-dev libpcap-dev libbz2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/openwall/john.git /opt/john \
    && cd /opt/john/src \
    && ./configure \
    && make -sj4

WORKDIR /opt/john/run
ENTRYPOINT ["./john"]
